import serial
import configparser
import os
import sys
import struct
import time
import threading
from datetime import datetime
from influxdb import InfluxDBClient
from flask import Flask, request, jsonify

api = Flask(__name__)

class OptolinkConnection:
    RESPONSE_ACK = 'ACK'
    REPONSE_NAK = 'NAK'
    RESPONSE_ENQ = 'ENQ'
    RESPONSE_UNKNOWN = 'UKN'

    def __init__(self, port):
        self.port = port
        self.connection = None
        self.in_vs2_mode = False
        self.lock = threading.Lock()
        self.connect()

    def connect(self):
        self.connection = serial.Serial(self.port, 4800, parity=serial.PARITY_EVEN, stopbits=2, timeout=5)

    def check_connection(self):
        if self.connection is None:
            raise Exception('Not connected')
        if not self.in_vs2_mode:
            if not self.initVS2():
                raise Exception('Communication error: InitVS2 mode failed')

    def tx(self, payload):
        self.check_connection()
        self.connection.write(payload)
        #print('wrote', payload)

    def rx(self, length):
        self.check_connection()
        response = self.connection.read(length)
        #if len(response) == 0:
        #    raise Exception('Timeout')
        #print('read', response)
        return response
    
    def initVS2(self):
        tries = 3
        success = False
        while tries > 0 and not success:
            tries = tries - 1
            # Terminate any existing VS2 connection to reset input state
            self.tx(b'\x04')
            # get rid of any remaining garbage in input buffer
            self.connection.reset_input_buffer()
            # wait for 0x05 idle signalling, alternatively accept ACK first (if we have been in VS2 state)
            data = self.rx(1)
            if data[0] != 0x05:
                if data[0] == 0x06:
                    data = self.rx(1)
                    if data[0] != 0x05:
                        continue
                else:
                    continue
            # send VS2 init sequence
            self.tx(b'\x16\x00\x00')
            if self.readAck() == OptolinkConnection.RESPONSE_ACK:
                success = True
        self.in_vs2_mode = success
        return success

    def sendTelegram(self, payload):
        length = len(payload)
        checksum = (sum(payload) + length) % 256
        telegram = struct.pack('BB', 0x41, length)
        telegram += payload
        telegram += struct.pack('B', checksum)
        self.tx(telegram)

    def readAck(self):
        ack = self.rx(1)
        if ack[0] == 0x15:
            return OptolinkConnection.REPONSE_NAK
        elif ack[0] == 0x05:
            return OptolinkConnection.RESPONSE_ENQ
        elif ack[0] == 0x06:
            return OptolinkConnection.RESPONSE_ACK
        else:
            return OptolinkConnection.RESPONSE_UNKNOWN        

    def readTelegram(self):
        if self.readAck() != OptolinkConnection.RESPONSE_ACK:
            # Transfer error: Reinit connection and abort this transfer
            self.initVS2()
            return None
        
        start = self.rx(1)
        if len(start) != 1 or start[0] != 0x41:
            self.initVS2()
            return None

        # length byte excluding checksum
        length = self.rx(1)
        if len(length) != 1:
            self.initVS2()
            return None

        payload = self.rx(length[0] + 1)
        if len(payload) != length[0] + 1:
            self.initVS2()
            return None
        
        checksum = payload[-1]
        calculated = (sum(payload[:-1]) + length[0]) % 256
        if checksum != calculated:
            self.initVS2()
            return None
        
        return payload[:-1]

    def readAddr(self, addr, cnt):
        with self.lock:
            request = struct.pack('>BBHB', 0, 1, addr, cnt)
            #print(request)
            self.sendTelegram(request)
            response = self.readTelegram()
            # todo: check first byte (response/error byte)
            if len(response) < 1:
                raise Exception('Read response does not match expected form', request, response)
            if response[0] != 0x01:
                if response[0] == 0x03:
                    # Error response: Return no data
                    return None
                raise Exception('Read response has unknown response type', request, response)
            if len(response) != 5 + cnt:
                raise Exception('Read payload length does not match expectation', request, response)
            if response[1:5] != request[1:5]:
                raise Exception('Read response does not match read request', request, response)
        return response [5:]

    def writeAddr(self, addr, data):
        with self.lock:
            request = struct.pack('>BBHB', 0, 2, addr, len(data)) + data
            self.sendTelegram(request)
            response = self.readTelegram()
            if len(response) != 5:
                raise Exception('Write response length does not match expectation', request, response)
            if response[0] != 0x01:
                if response[0] == 0x03:
                    # Error response: Write did not succeed
                    return False
                raise Exception('Write response has unknown response type', request, response)
            if response[1:5] != request[1:5]:
                raise Exception('Write response does not match write request', request, response)
        return True


class Transformations:
    def shortToInt(v):
        return (struct.unpack('<h', v))[0]

    def temperatureShortToFloat(v):
        return Transformations.shortToInt(v) / 10

    def byteToInt(v):
        return v[0]

    def percentageByteToFloat(v):
        return v[0] / 2

    def intToInt(v):
        return (struct.unpack('<l', v))[0]

    def int64ToInt(v):
        return (struct.unpack('<q', v))[0]

@api.route('/api/<address>', methods=['GET', 'POST'])
def access(address):
    address = int(address, 16)
    size = 2
    if address < 0 or address > 0xFFFF or size < 1 or size > 16:
        abort(400)

    if request.method == 'POST':
        if request.json is not None:
            data = request.json.get('data')
            if data.startswith('0x'):
                data = data[2:]
            data = bytes.fromhex(data)
            optolink.writeAddr(address, data)
            size = len(data)
        
    if request.method == 'GET':
        size = request.args.get('size', '2')
        size = int(size, 10)
        if size < 1 or size > 16:
                abort(400)    

    result = optolink.readAddr(address, size)

    if size == 1:
        human_readable = Transformations.byteToInt(result)
    elif size == 2:
        human_readable = Transformations.shortToInt(result)
    elif size == 4:
        human_readable = Transformations.intToInt(result)
    elif size == 8:
        human_readable = Transformations.int64ToInt(result)
    else:
        human_readable = '?'

    return jsonify({
        'address': address,
        'data': result.hex(),
        'humanReadable': human_readable
    })

def influxdb_log(optolink, influx):
    readings = [
        ['KTS', 'temperatureShortToFloat', 0x0802, 2],
        ['ATS', 'temperatureShortToFloat', 0x0800, 2],
        ['RL17A', 'temperatureShortToFloat', 0x080A, 2],
        ['KTS_soll', 'temperatureShortToFloat', 0x555A, 2],
        ['Pact', 'percentageByteToFloat', 0xA38F, 1],
        ['StorTop', 'temperatureShortToFloat', 0x0804, 2]
    ]

    while True:
        fields = {}
        for e in readings:
            v = optolink.readAddr(e[2], e[3])
            transformation = getattr(Transformations, e[1])
            transformed = transformation(v)
            fields[e[0]] = transformed
        data = {
            'measurement': 'vitolink',
            'time': datetime.utcnow().isoformat(),
            'fields': fields
        }
        influx.write_points([data], time_precision='ms')
        time.sleep(5)

def main():
    config = configparser.ConfigParser()
    config.read(os.path.join(os.path.dirname(__file__), 'defaults.ini'))

    influx = InfluxDBClient(host=config.get('influxdb', 'host'), port=8086, username='', password='', database=config.get('influxdb', 'database'), ssl=False, verify_ssl=False, retries=20, timeout=60)

    optolink = OptolinkConnection(config.get('serial', 'port'))

    influxdb_log_thread = threading.Thread(None, influxdb_log, "InfluxDB-Log", (optolink, influx))
    influxdb_log_thread.start()
    api.run(debug=True)


if __name__ == '__main__':
     main()

"""
#print('KTS:', temperatureShortToFloat(readAddr(ser, 0x0802, 2)))
#print('ATS:', temperatureShortToFloat(readAddr(ser, 0x0800, 2)))
#print('RL17A:', temperatureShortToFloat(readAddr(ser, 0x080A, 2)))
#print('Leistung:', percentageByteToFloat(readAddr(ser, 0xA38F, 1)))
#print('Ksoll?:', temperatureShortToFloat(readAddr(ser, 0x555A, 2)))




#for i in range(0, 255, 1):
#    try:
#        print('0x33%02x' % (i), byteToInt(readAddr(ser, 0x3300 + i, 1)))
#    except:
#       pass
"""
import serial
import configparser
import os
import sys
import struct
import time
from datetime import datetime
from influxdb import InfluxDBClient

def tx(ser, payload):
    ser.write(payload)
    #print('wrote', payload)

def rx(ser, length):
    response = ser.read(length)
    if len(response) == 0:
        raise Exception('Timeout')
    #print('read', response)
    return response

def sendTelegram(ser, payload):
    length = len(payload)
    checksum = (sum(payload) + length) % 256
    telegram = struct.pack('BB', 0x41, length)
    telegram += payload
    telegram += struct.pack('B', checksum)
    tx(ser, telegram)

def expectAck(ser):
    ack = rx(ser, 1)
    if ack[0] == 0x15:
        raise Exception('Expected ACK, got NACK')
    elif ack[0] == 0x05:
        raise Exception('Expected ACK, got ENQ')
    elif ack[0] == 0x06:
        return
    else:
        raise Exception('Expected ACK, got', ack)

def readTelegram(ser):
    expectAck(ser)
    
    start = rx(ser, 1)
    if start[0] != 0x41:
        raise Exception('Error: Expected ack, got ', start)

    # length byte excluding checksum
    length = rx(ser, 1)

    payload = rx(ser, length[0] + 1)
    if len(payload) != length[0] + 1:
            raise Exception('Communication Error')
    
    checksum = payload[-1]
    calculated = (sum(payload[:-1]) + length[0]) % 256
    if checksum != calculated:
        raise Exception('Checksum error')
    
    return payload[:-1]

def readAddr(ser, addr, cnt):
    request = struct.pack('>BBHB', 0, 1, addr, cnt)
    #print(request)
    sendTelegram(ser, request)
    response = readTelegram(ser)
    if len(response) != 5 + cnt:
        raise Exception('Read payload length does not match expectation', request, response)
    if response[0] != 0x01 or response[1:5] != request[1:5]:
        raise Exception('Read response does not match read request', request, response)

    return response [5:]

class Transformations:
    def shortToInt(v):
        return (struct.unpack('<h', v))[0]

    def temperatureShortToFloat(v):
        return Transformations.shortToInt(v) / 10

    def byteToInt(v):
        return v[0]

    def percentageByteToFloat(v):
        return v[0] / 2

config = configparser.ConfigParser()
config.read(os.path.join(os.path.dirname(__file__), 'defaults.ini'))

influx = InfluxDBClient(host=config.get('influxdb', 'host'), port=8086, username='', password='', database=config.get('influxdb', 'database'), ssl=False, verify_ssl=False, retries=20, timeout=60)

ser = serial.Serial(config.get('serial', 'port'), 4800, parity=serial.PARITY_EVEN, stopbits=2, timeout=5)

tx(ser, b'\x04')
ser.reset_input_buffer()
data = rx(ser, 1)
if data[0] != 0x05:
    if data[0] == 0x06:
        data = rx(ser, 1)
        if data[0] != 0x05:
            print('Error: Expected 0x05, got ', data)
    else:
        print('Error: Expected 0x05 or 0x06, got ', data)
        sys.exit(1)

tx(ser, b'\x16\x00\x00')
expectAck(ser)
    
print('Initialized VS2 communication')

#print('KTS:', temperatureShortToFloat(readAddr(ser, 0x0802, 2)))
#print('ATS:', temperatureShortToFloat(readAddr(ser, 0x0800, 2)))
#print('RL17A:', temperatureShortToFloat(readAddr(ser, 0x080A, 2)))
#print('Leistung:', percentageByteToFloat(readAddr(ser, 0xA38F, 1)))
#print('Ksoll?:', temperatureShortToFloat(readAddr(ser, 0x555A, 2)))

readings = [
    ['KTS', 'temperatureShortToFloat', 0x0802, 2],
    ['ATS', 'temperatureShortToFloat', 0x0800, 2],
    ['RL17A', 'temperatureShortToFloat', 0x080A, 2],
    ['KTS_soll', 'temperatureShortToFloat', 0x555A, 2],
    ['Pact', 'percentageByteToFloat', 0xA38F, 1]
]

while True:
    fields = {}
    for e in readings:
        v = readAddr(ser, e[2], e[3])
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


#for i in range(0, 255, 1):
#    try:
#        print('0x33%02x' % (i), byteToInt(readAddr(ser, 0x3300 + i, 1)))
#    except:
#       pass
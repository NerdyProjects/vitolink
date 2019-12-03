let datapointlist =
  [
    {
      "address": "0x0800",
      "name": "ATS",
      "size": 2,
    },
    {
      "address": "0x0810",
      "name": "KTS",
      "size": 2,
    },
    {
      "address": "0x0818",
      "name": "RL17A",
      "size": 2,
    },
    {
      "address": "0x0818",
      "name": "RL17A",
      "size": 2,
    },
    {
      "address": "0x3303",
      "name": "M2 Party",
      "size": 1,
    },
    {
      "address": "0x3304",
      "name": "M2 Niveau",
      "size": 1,
    },
    {
      "address": "0x3305",
      "name": "M2 Neigung",
      "size": 1,
    },
    {
      "address": "0x3306",
      "name": "M2 RTsoll",
      "size": 1,
    },
    {
      "address": "0x3307",
      "name": "M2 RTsollred",
      "size": 1,
    },
    {
      "address": "0x3308",
      "name": "M2 RTsollparty",
      "size": 1,
    }
  ]

async function fetchAddress (addr, size = 2) {
  const res = await fetch (`/api/${addr}?size=${size}`)
  const data = await res.json()
  return data
}

async function setAddress (addr, data) {
  const res = await fetch (`/api/${addr}`, {
    method: 'POST',
    headers: {'Content-Type': 'application/json'},
    body: JSON.stringify({data: data})
  })
  const result = await res.json()
  return result
}

function zeroPad(val, digits = 2) {
  return ('00000000000000000' + val).slice(-digits)
}

function swapEndianess(v) {
  const result = []
  let len = v.length - 2
  while (len >= 0) {
    result.push(v.substr(len, 2))
    len -= 2
  }
  return result.join('')
}

async function start (Component, routes) {
  const router = new VueRouter({routes})
  const app = new Vue({
    router,
    render: h => h(Component)
  }).$mount('#app')
}

function isAbortError(err) {
  return err.name === 'AbortError'
}

const UApp = {
  template: `
    <div>
      <nav class="navbar" role="navigation" aria-label="main navigation">
        <div class="navbar-brand">
          <router-link class="navbar-item" :to="{ name: 'debug' }">debug</router-link>
        </div>
      </nav>

      <RouterView></RouterView>
    </div>
  `
}


const UDebug = {
  data() {
    return {
      address: '0x0800',
      size: 2,
      data: null,
      sdata: null,
      udata: null,
      datapointlist: datapointlist,
    }
  },
  methods: {
    async submit() {
      data = await setAddress(this.address, this.data)
      this.data = data.data
      this.updateFromData()
    },
    async refresh() {
      data = await fetchAddress(this.address, this.size)
      this.data = data.data
      this.updateFromData()
    },
    updateFromData() {
      data = swapEndianess(this.data)
      this.udata = parseInt(data, 16)
    },
    updateFromUData() {
      this.data = swapEndianess(zeroPad(parseInt(this.udata).toString(16), 2 * this.size))
    },
    updateFromEntry(entry) {
      this.address = entry.address
      this.size = entry.size
      this.refresh()
    }
  },
  template: `
    <div class="UDebugControl">
      <ul>
        <li v-for="entry in datapointlist">
          <label @click="updateFromEntry(entry)">{{ entry.name }}</label>
        </li>
      </ul>
      <form @submit="submit">
        <div class="field">
          <label class="label is-large">Address</label>
          <div class="control">
            <input class="input is-large" type="text" v-model="address">
          </div>
        </div>

        <div class="field">
          <label class="label is-large">Data (Hex)</label>
          <div class="control">
            <input class="input is-large" type="text" @change="updateFromData" v-model="data">
          </div>
        </div>

        <div class="field">
          <label class="label is-large">Data (Unsigned)</label>
          <div class="control">
            <input class="input is-large" type="text" @change="updateFromUData" v-model="udata">
          </div>
        </div>

        <div class="field">
          <label class="label is-large">Size</label>
          <div class="control">
            <input class="input is-large" type="text" v-model="size">
          </div>
        </div>

        <div class="field is-grouped is-grouped-right">
        <p class="control">
          <button class="button is-large" @click.stop.prevent="refresh">refresh</button>
        </p>
        <p class="control">
          <button class="button is-large" type="submit">set</button>
        </p>
        </div>
      </div>
      </form>
    </div>
  `
}

const routes = [
  {
    path: '/',
    redirect: { name: 'debug' }
  },
  {
    path: '/debug',
    component: UDebug,
    name: 'debug',
  },
]

start(UApp, routes)
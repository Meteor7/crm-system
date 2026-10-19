import { createPinia } from 'pinia'
import { createApp } from 'vue'
import App from './App.vue'
import { router } from './app/router'
import './design-system/tokens.css'
import './design-system/base.css'
import './design-system/workspace.css'
import './design-system/typography.css'

createApp(App).use(createPinia()).use(router).mount('#app')

import './design-system/qiheng.css'

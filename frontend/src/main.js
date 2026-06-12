// 文件说明：前端应用入口，创建 Vue 应用并挂载 Element Plus。
import { createApp } from 'vue'
import ElementPlus from 'element-plus'
import 'element-plus/dist/index.css'
import App from './App.vue'
import './styles.css'

createApp(App).use(ElementPlus).mount('#app')

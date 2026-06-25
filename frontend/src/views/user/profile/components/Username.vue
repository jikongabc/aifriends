<script setup>
// 用户名输入框：本地维护输入值并暴露给父组件。
import {ref, watch} from "vue";

const props = defineProps(['username'])
const myUsername = ref(props.username)

watch(() => props.username, newVal => {
  myUsername.value = newVal
})

defineExpose({
  myUsername,
})
</script>

<template>
  <fieldset class="fieldset">
    <label class="label text-base">用户名</label>
    <input v-model="myUsername" type="text" class="input w-108">
  </fieldset>
</template>

<style scoped>

</style>
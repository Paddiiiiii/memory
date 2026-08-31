<template>
  <div class="login">
    <h1>回忆录访谈 Copilot</h1>
    <p class="sub">专业访谈者桌面辅助 · V1</p>
    <form @submit.prevent="onSubmit">
      <label>邮箱<input v-model="email" type="email" required /></label>
      <label>密码<input v-model="password" type="password" required /></label>
      <button class="primary" type="submit" :disabled="loading">登录</button>
      <p v-if="error" class="err">{{ error }}</p>
    </form>
  </div>
</template>

<script setup lang="ts">
import { ref } from "vue";
import { useRouter } from "vue-router";
import { AuthApi } from "../lib/api";

const router = useRouter();
const email = ref("admin@example.com");
const password = ref("");
const loading = ref(false);
const error = ref("");

async function onSubmit() {
  loading.value = true;
  error.value = "";
  try {
    const tokens = await AuthApi.login(email.value, password.value);
    localStorage.setItem("access_token", tokens.access_token);
    localStorage.setItem("refresh_token", tokens.refresh_token);
    await router.push("/projects");
  } catch (e) {
    error.value = e instanceof Error ? e.message : String(e);
  } finally {
    loading.value = false;
  }
}
</script>

<style scoped>
.login {
  max-width: 380px;
  margin: 12vh auto;
  padding: 2rem;
  background: var(--panel);
  border: 1px solid var(--line);
  border-radius: 10px;
}
h1 { font-size: 1.4rem; margin: 0 0 0.25rem; font-weight: 600; }
.sub { color: var(--muted); margin: 0 0 1.5rem; }
form { display: grid; gap: 0.85rem; }
label { display: grid; gap: 0.35rem; font-size: 0.9rem; color: var(--muted); }
.err { color: var(--danger); font-size: 0.85rem; }
</style>

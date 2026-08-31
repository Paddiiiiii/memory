<template>
  <div class="page">
    <header>
      <h1>项目</h1>
      <div class="actions">
        <button @click="load">刷新</button>
        <button class="primary" @click="showCreate = true">新建项目</button>
      </div>
    </header>
    <p v-if="err" class="err">{{ err }}</p>
    <ul class="list">
      <li v-for="p in projects" :key="p.id">
        <div>
          <strong>{{ p.title }}</strong>
          <span class="muted">{{ p.subject?.display_name }}</span>
        </div>
        <button class="primary" @click="startSession(p.id)">开始访谈准备</button>
      </li>
    </ul>

    <div v-if="showCreate" class="modal">
      <div class="card">
        <h2>新建项目（一位老人）</h2>
        <label>项目标题<input v-model="title" /></label>
        <label>受访者称呼/化名<input v-model="name" /></label>
        <label class="check"><input v-model="consentA" type="checkbox" /> 同意录音（Consent A）</label>
        <label class="check"><input v-model="consentB" type="checkbox" /> 同意云端 AI/ASR（Consent B）</label>
        <p v-if="!consentB" class="hint">不勾选 B 将进入「仅本地录音模式」。</p>
        <div class="row">
          <button @click="showCreate = false">取消</button>
          <button class="primary" :disabled="!consentA || creating" @click="create">创建</button>
        </div>
      </div>
    </div>
  </div>
</template>

<script setup lang="ts">
import { onMounted, ref } from "vue";
import { useRouter } from "vue-router";
import { ProjectApi, SessionApi } from "../lib/api";

const router = useRouter();
const projects = ref<Array<{ id: string; title: string; subject?: { display_name: string } }>>([]);
const err = ref("");
const showCreate = ref(false);
const title = ref("");
const name = ref("");
const consentA = ref(false);
const consentB = ref(true);
const creating = ref(false);

async function load() {
  try {
    projects.value = await ProjectApi.list();
  } catch (e) {
    err.value = e instanceof Error ? e.message : String(e);
    if (String(err.value).includes("401") || String(err.value).includes("未登录")) {
      router.push("/login");
    }
  }
}

async function create() {
  creating.value = true;
  try {
    const p = (await ProjectApi.create(title.value || `${name.value}的回忆录`, name.value)) as {
      id: string;
    };
    await ProjectApi.consent(p.id, "RECORDING", true);
    await ProjectApi.consent(p.id, "CLOUD_AI_PROCESSING", consentB.value);
    showCreate.value = false;
    await load();
  } catch (e) {
    err.value = e instanceof Error ? e.message : String(e);
  } finally {
    creating.value = false;
  }
}

async function startSession(projectId: string) {
  const s = await SessionApi.create(projectId);
  await SessionApi.ready(s.id);
  router.push(`/interview/${s.id}`);
}

onMounted(load);
</script>

<style scoped>
.page { max-width: 900px; margin: 0 auto; padding: 1.5rem; }
header { display: flex; justify-content: space-between; align-items: center; }
.list { list-style: none; padding: 0; display: grid; gap: 0.75rem; }
.list li {
  display: flex; justify-content: space-between; align-items: center;
  background: var(--panel); border: 1px solid var(--line); padding: 1rem; border-radius: 8px;
}
.muted { color: var(--muted); margin-left: 0.75rem; font-size: 0.9rem; }
.modal {
  position: fixed; inset: 0; background: rgba(0,0,0,.35);
  display: grid; place-items: center;
}
.card {
  width: min(420px, 92vw); background: var(--panel); padding: 1.25rem;
  border-radius: 10px; display: grid; gap: 0.75rem;
}
.row { display: flex; gap: 0.5rem; justify-content: flex-end; }
.check { display: flex; align-items: center; gap: 0.5rem; }
.hint { color: var(--warn); font-size: 0.85rem; margin: 0; }
.err { color: var(--danger); }
</style>

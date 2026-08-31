import { createRouter, createWebHistory } from "vue-router";
import LoginView from "./views/LoginView.vue";
import ProjectsView from "./views/ProjectsView.vue";
import InterviewView from "./views/InterviewView.vue";

export const router = createRouter({
  history: createWebHistory(),
  routes: [
    { path: "/", redirect: "/projects" },
    { path: "/login", component: LoginView },
    { path: "/projects", component: ProjectsView },
    { path: "/interview/:sessionId", component: InterviewView, props: true },
  ],
});

/**
 * 全局任务管理 — 页面切换不中断任务追踪
 *
 * 支持 listing / review / social 三种工作流。
 * 任务添加后后台轮询，组件挂载/卸载不影响。
 * 任务完成后保留结果，组件重新挂载时可立即读取。
 */

import { API_BASE } from "./utils";

export type WorkflowType = "listing" | "review" | "social";

export interface TaskInfo {
  id: string;
  type: WorkflowType;
  status: "running" | "awaiting_review" | "completed" | "failed" | "rejected";
  product_name?: string;
  product_asin?: string;
  progress?: string;
  current_step?: string;
  result?: any;
  error?: string;
}

type Listener = () => void;

const API_PATHS: Record<WorkflowType, string> = {
  listing: "listing",
  review: "reviews",
  social: "social",
};

class TaskStore {
  private tasks: Map<string, TaskInfo> = new Map();
  private listeners: Set<Listener> = new Set();
  private pollers: Map<string, ReturnType<typeof setInterval>> = new Map();

  subscribe(fn: Listener): () => void {
    this.listeners.add(fn);
    return () => { this.listeners.delete(fn); };
  }

  private notify() {
    this.listeners.forEach((fn) => fn());
  }

  getAll(): TaskInfo[] {
    return Array.from(this.tasks.values());
  }

  get(id: string): TaskInfo | undefined {
    return this.tasks.get(id);
  }

  /** 添加任务并开始后台轮询 */
  add(task: TaskInfo) {
    this.tasks.set(task.id, task);
    this.notify();
    this.startPolling(task.id, task.type);
  }

  /** 手动刷新某个任务 */
  async refresh(id: string) {
    const task = this.tasks.get(id);
    if (!task) return;
    if (["completed", "failed", "rejected"].includes(task.status)) return;

    const apiPath = API_PATHS[task.type];
    try {
      const res = await fetch(`${API_BASE}/${apiPath}/${id}/status`);
      if (!res.ok) return;
      const data = await res.json();
      this.tasks.set(id, {
        ...task,
        status: data.status,
        current_step: data.current_step,
        progress: data.current_step,
        error: data.error,
      });

      if (["awaiting_review", "completed"].includes(data.status)) {
        const resultRes = await fetch(`${API_BASE}/${apiPath}/${id}/result`);
        if (resultRes.ok) {
          const resultData = await resultRes.json();
          const current = this.tasks.get(id)!;
          this.tasks.set(id, { ...current, status: data.status, result: resultData });
        }
      }
      this.notify();
    } catch {
      // 忽略网络错误
    }
  }

  private startPolling(taskId: string, type: WorkflowType) {
    if (this.pollers.has(taskId)) return;

    const interval = setInterval(async () => {
      const task = this.tasks.get(taskId);
      if (!task) {
        this.stopPolling(taskId);
        return;
      }
      await this.refresh(taskId);
      const updated = this.tasks.get(taskId);
      if (updated && ["completed", "failed", "awaiting_review", "rejected"].includes(updated.status)) {
        this.stopPolling(taskId);
      }
    }, 3000);

    this.pollers.set(taskId, interval);
  }

  private stopPolling(taskId: string) {
    const interval = this.pollers.get(taskId);
    if (interval) {
      clearInterval(interval);
      this.pollers.delete(taskId);
    }
  }

  remove(id: string) {
    this.stopPolling(id);
    this.tasks.delete(id);
    this.notify();
  }
}

// ═══════════════════════════════════════════════════════════
// 客服会话持久化（页面切换不丢失）
// ═══════════════════════════════════════════════════════════

export interface ChatMessage {
  id?: string;
  role: "customer" | "agent" | "system";
  content: string;
  intent?: string;
  auto_reply?: boolean;
}

export interface ConversationState {
  conversationId: string;
  customerId: string;
  messages: ChatMessage[];
}

class ConversationStore {
  private conversations: Map<string, ConversationState> = new Map();
  private listeners: Set<Listener> = new Set();

  subscribe(fn: Listener): () => void {
    this.listeners.add(fn);
    return () => { this.listeners.delete(fn); };
  }

  private notify() {
    this.listeners.forEach((fn) => fn());
  }

  get(conversationId: string): ConversationState | undefined {
    return this.conversations.get(conversationId);
  }

  getLatest(): ConversationState | undefined {
    let latest: ConversationState | undefined;
    for (const c of this.conversations.values()) {
      if (!latest || c.messages.length > latest.messages.length) {
        latest = c;
      }
    }
    return latest;
  }

  set(conversationId: string, state: ConversationState) {
    this.conversations.set(conversationId, state);
    this.notify();
  }

  remove(conversationId: string) {
    this.conversations.delete(conversationId);
    this.notify();
  }
}

export const taskStore = new TaskStore();
export const conversationStore = new ConversationStore();

import { useState, useRef, useEffect } from "react";
import { API_BASE } from "../lib/utils";
import { conversationStore, type ChatMessage } from "../lib/TaskStore";
import { Send, MessageSquare, AlertCircle, Check, Clock, Ticket, RefreshCw, Mic, MicOff } from "lucide-react";

interface TicketInfo {
  id: string;
  conversation_id: string | null;
  priority: string;
  summary: string;
  suggested_action: string | null;
  status: string;
  assigned_to: string | null;
  created_at: string;
}

export default function CustomerServicePage() {
  const [customerId, setCustomerId] = useState("demo-user-001");
  const [conversationId, setConversationId] = useState<string | null>(null);
  const [messages, setMessages] = useState<ChatMessage[]>([]);
  const [input, setInput] = useState("");
  const [isListening, setIsListening] = useState(false);
  const recognitionRef = useRef<any>(null);
  const [loading, setLoading] = useState(false);
  const [hasHistory, setHasHistory] = useState(false);
  const [streamingText, setStreamingText] = useState("");
  const [currentStep, setCurrentStep] = useState("");
  const [activeTab, setActiveTab] = useState<"chat" | "tickets">("chat");
  const [tickets, setTickets] = useState<TicketInfo[]>([]);
  const [ticketLoading, setTicketLoading] = useState(false);
  const [lastTicketId, setLastTicketId] = useState<string | null>(null);
  const [savedConvs, setSavedConvs] = useState(conversationStore.getAll());
  const chatEndRef = useRef<HTMLDivElement>(null);

  const refreshSavedConvs = () => setSavedConvs(conversationStore.getAll());

  const restoreConversation = (convId: string, custId: string, msgs: ChatMessage[]) => {
    setConversationId(convId);
    setCustomerId(custId);
    setMessages(msgs);
    setHasHistory(true);
  };

  const deleteConversation = (convId: string) => {
    conversationStore.remove(convId);
    refreshSavedConvs();
    if (conversationId === convId) {
      setConversationId(null);
      setMessages([]);
      setHasHistory(false);
    }
  };

  useEffect(() => {
    return conversationStore.subscribe(() => {
      if (conversationId) {
        const saved = conversationStore.get(conversationId);
        if (saved) setMessages([...saved.messages]);
      }
    });
  }, [conversationId]);

  useEffect(() => {
    chatEndRef.current?.scrollIntoView({ behavior: "smooth" });
  }, [messages, streamingText]);

  const persist = (msgs: ChatMessage[]) => {
    if (conversationId) {
      conversationStore.set(conversationId, {
        conversationId,
        customerId,
        messages: msgs,
      });
      refreshSavedConvs();
    }
  };

  const fetchTickets = async () => {
    setTicketLoading(true);
    try {
      const res = await fetch(`${API_BASE}/conversations/tickets`);
      if (res.ok) setTickets(await res.json());
    } catch {}
    setTicketLoading(false);
  };

  const updateTicket = async (ticketId: string, updates: Record<string, string>) => {
    try {
      const res = await fetch(`${API_BASE}/conversations/tickets/${ticketId}`, {
        method: "PATCH",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify(updates),
      });
      if (res.ok) await fetchTickets();
    } catch {}
  };

  const initConversation = async () => {
    const res = await fetch(`${API_BASE}/conversations/`, {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ customer_id: customerId, language: "zh" }),
    });
    const data = await res.json();
    setConversationId(data.id);
    setMessages([]);
    setHasHistory(false);
    persist([]);
  };

  const toggleVoice = () => {
    const SpeechRecognition = (window as any).SpeechRecognition || (window as any).webkitSpeechRecognition;
    if (!SpeechRecognition) {
      alert("你的浏览器不支持语音识别，请使用 Chrome");
      return;
    }

    if (isListening) {
      recognitionRef.current?.stop();
      setIsListening(false);
      return;
    }

    const recognition = new SpeechRecognition();
    recognition.lang = "zh-CN"; // 默认中文，可切换
    recognition.interimResults = false;
    recognition.continuous = false;
    recognition.maxAlternatives = 1;

    recognition.onresult = (event: any) => {
      const transcript = event.results[0][0].transcript;
      setInput((prev) => prev + transcript);
    };

    recognition.onerror = (event: any) => {
      console.error("语音识别错误:", event.error);
      setIsListening(false);
    };

    recognition.onend = () => {
      setIsListening(false);
    };

    recognitionRef.current = recognition;
    recognition.start();
    setIsListening(true);
  };

  const sendMessage = async () => {
    if (!input.trim() || !conversationId) return;

    const userMsg: ChatMessage = { role: "customer", content: input };
    const newMsgs = [...messages, userMsg];
    setMessages(newMsgs);
    persist(newMsgs);
    setInput("");
    setLoading(true);
    setStreamingText("");
    setCurrentStep("");

    try {
      const res = await fetch(
        `${API_BASE}/conversations/${conversationId}/messages/stream`,
        {
          method: "POST",
          headers: { "Content-Type": "application/json" },
          body: JSON.stringify({ content: userMsg.content }),
        }
      );

      if (!res.ok) {
        const err = await res.json().catch(() => ({ detail: "请求失败" }));
        throw new Error(err.detail);
      }

      const reader = res.body!.getReader();
      const decoder = new TextDecoder();
      let buffer = "";
      let fullReply = "";
      let finalIntent = "";
      let finalAutoReply = false;
      let currentEventType = "";

      while (true) {
        const { done, value } = await reader.read();
        if (done) break;

        buffer += decoder.decode(value, { stream: true });
        const lines = buffer.split("\n");
        buffer = lines.pop() || "";

        for (const line of lines) {
          if (line.startsWith("event: ")) {
            currentEventType = line.slice(7).trim();
          } else if (line.startsWith("data: ")) {
            const data = JSON.parse(line.slice(6));

            if (currentEventType === "progress" && data.step === "intent_done") {
              setCurrentStep(`识别意图: ${data.intent} (${Math.round(data.confidence * 100)}%)`);
            } else if (currentEventType === "progress" && data.step === "rag_done") {
              setCurrentStep(`检索到 ${data.chunks_found} 条相关知识`);
            } else if (currentEventType === "token" && data.token !== undefined) {
              setCurrentStep("");
              fullReply += data.token;
              setStreamingText(fullReply);
            } else if (currentEventType === "done") {
              finalIntent = data.intent || "";
              finalAutoReply = data.auto_reply || false;
              if (data.ticket_id) {
                setLastTicketId(data.ticket_id);
              }
            }
          }
        }
      }

      if (fullReply) {
        const agentMsg: ChatMessage = {
          id: crypto.randomUUID(),
          role: "agent",
          content: fullReply,
          intent: finalIntent || undefined,
          auto_reply: finalAutoReply,
        };
        const updated = [...newMsgs, agentMsg];
        setMessages(updated);
        persist(updated);
      } else {
        const errMsg: ChatMessage = {
          role: "system",
          content: "Agent 未能生成回复，请重试",
        };
        const updated = [...newMsgs, errMsg];
        setMessages(updated);
        persist(updated);
      }
    } catch (err: any) {
      const errMsg: ChatMessage = {
        role: "system",
        content: err.message || "发送失败，请重试",
      };
      const updated = [...newMsgs, errMsg];
      setMessages(updated);
      persist(updated);
    }

    setLoading(false);
    setStreamingText("");
    setCurrentStep("");
  };

  const startNewChat = () => {
    setConversationId(null);
    setMessages([]);
    setHasHistory(false);
    setActiveTab("chat");
  };

  const priorityBadge = (p: string) => {
    const map: Record<string, string> = {
      urgent: "bg-red-100 text-red-700 border-red-200",
      high: "bg-orange-100 text-orange-700 border-orange-200",
      medium: "bg-yellow-100 text-yellow-700 border-yellow-200",
      low: "bg-slate-100 text-slate-500 border-slate-200",
    };
    return map[p] || map.low;
  };

  const statusBadge = (s: string) => {
    const map: Record<string, string> = {
      open: "bg-red-50 text-red-600",
      in_progress: "bg-blue-50 text-blue-600",
      resolved: "bg-green-50 text-green-600",
      closed: "bg-slate-50 text-slate-400",
    };
    return map[s] || map.open;
  };

  return (
    <div>
      <div className="flex items-center justify-between mb-4">
        <h1 className="text-2xl font-bold text-slate-900">智能客服</h1>
        {conversationId && (
          <div className="flex items-center gap-2">
            {/* Tab switcher */}
            <div className="flex bg-slate-100 rounded-lg p-0.5">
              {(["chat", "tickets"] as const).map((tab) => (
                <button
                  key={tab}
                  onClick={() => {
                    setActiveTab(tab);
                    if (tab === "tickets") fetchTickets();
                  }}
                  className={`px-3 py-1 rounded-md text-xs font-medium transition-colors ${
                    activeTab === tab ? "bg-white text-slate-900 shadow-sm" : "text-slate-500 hover:text-slate-700"
                  }`}
                >
                  {tab === "chat" ? "对话" : "工单"}
                </button>
              ))}
            </div>
            <button
              onClick={startNewChat}
              className="text-sm text-blue-600 hover:text-blue-800 flex items-center gap-1"
            >
              <MessageSquare size={14} /> 新建对话
            </button>
          </div>
        )}
      </div>

      {/* 工单创建提示 */}
      {lastTicketId && activeTab === "chat" && (
        <div className="flex items-center justify-between bg-amber-50 border border-amber-200 rounded-lg px-4 py-2 mb-4">
          <div className="flex items-center gap-2 text-sm text-amber-700">
            <AlertCircle size={14} />
            已自动创建工单，需要人工跟进处理
          </div>
          <button
            onClick={() => { setActiveTab("tickets"); fetchTickets(); setLastTicketId(null); }}
            className="text-xs text-amber-700 font-medium hover:text-amber-900 underline"
          >
            查看工单
          </button>
        </div>
      )}

      {!conversationId ? (
        <div className="max-w-md mx-auto space-y-4">
          <div className="bg-white rounded-xl border border-slate-200 p-6">
            <h3 className="text-sm font-medium text-gray-600 mb-3">新建会话</h3>
            <input type="text" value={customerId} onChange={(e) => setCustomerId(e.target.value)} placeholder="Customer ID" className="w-full px-3 py-2 border border-slate-300 rounded-lg text-sm mb-3" />
            <button onClick={initConversation} disabled={!customerId.trim()} className="w-full bg-blue-600 text-white py-2 rounded-lg font-medium hover:bg-blue-700 disabled:opacity-50 transition-colors">Start Chat</button>
          </div>
          {savedConvs.length > 0 && (
            <div className="bg-white rounded-xl border border-slate-200 p-4">
              <h3 className="text-sm font-medium text-gray-600 mb-2">历史会话 ({savedConvs.length})</h3>
              <div className="space-y-2 max-h-64 overflow-auto">
                {savedConvs.map((conv) => (
                  <div key={conv.conversationId} className="flex items-center gap-2 p-2 bg-gray-50 rounded-lg text-xs">
                    <button onClick={() => restoreConversation(conv.conversationId, conv.customerId, conv.messages)} className="flex-1 text-left hover:bg-gray-100 p-1 rounded">
                      <span className="font-medium">{conv.customerId}</span>
                      <span className="text-gray-400 ml-2">{conv.messages.length} msgs</span>
                    </button>
                    <button onClick={() => deleteConversation(conv.conversationId)} className="text-red-400 hover:text-red-600 px-1">x</button>
                  </div>
                ))}
              </div>
            </div>
          )}
        </div>
      ) : activeTab === "tickets" ? (
        /* 工单面板 */
        <div className="max-w-2xl bg-white rounded-xl border border-slate-200">
          <div className="flex items-center justify-between p-4 border-b border-slate-100">
            <h2 className="font-semibold text-slate-700 flex items-center gap-2">
              <Ticket size={16} /> 工单列表
            </h2>
            <button
              onClick={fetchTickets}
              disabled={ticketLoading}
              className="flex items-center gap-1 text-xs text-slate-500 hover:text-slate-700"
            >
              <RefreshCw size={12} className={ticketLoading ? "animate-spin" : ""} />
              刷新
            </button>
          </div>

          {tickets.length === 0 ? (
            <div className="text-center py-12 text-sm text-slate-400">
              <Ticket size={32} className="mx-auto mb-3 text-slate-300" />
              暂无工单
            </div>
          ) : (
            <div className="divide-y divide-slate-50 max-h-[600px] overflow-auto">
              {tickets.map((t) => (
                <div key={t.id} className="p-4 hover:bg-slate-50 transition-colors">
                  <div className="flex items-start justify-between mb-2">
                    <div className="flex items-center gap-2 min-w-0">
                      <span className={`text-xs px-1.5 py-0.5 rounded border font-medium ${priorityBadge(t.priority)}`}>
                        {t.priority.toUpperCase()}
                      </span>
                      <span className={`text-xs px-1.5 py-0.5 rounded ${statusBadge(t.status)}`}>
                        {t.status === "open" ? "待处理" : t.status === "in_progress" ? "处理中" : t.status === "resolved" ? "已解决" : "已关闭"}
                      </span>
                    </div>
                    <span className="text-xs text-slate-400 shrink-0 ml-2">
                      {new Date(t.created_at).toLocaleString("zh-CN")}
                    </span>
                  </div>

                  <p className="text-sm text-slate-700 mb-1">{t.summary || "无摘要"}</p>
                  {t.suggested_action && (
                    <p className="text-xs text-blue-600 bg-blue-50 rounded px-2 py-1 mt-2">
                      建议操作: {t.suggested_action}
                    </p>
                  )}

                  {/* Actions */}
                  {t.status === "open" && (
                    <div className="flex gap-2 mt-3">
                      <button
                        onClick={() => updateTicket(t.id, { status: "in_progress" })}
                        className="flex items-center gap-1 text-xs px-2 py-1 bg-blue-50 text-blue-600 rounded hover:bg-blue-100 transition-colors"
                      >
                        <Clock size={12} /> 开始处理
                      </button>
                      <button
                        onClick={() => updateTicket(t.id, { status: "resolved" })}
                        className="flex items-center gap-1 text-xs px-2 py-1 bg-green-50 text-green-600 rounded hover:bg-green-100 transition-colors"
                      >
                        <Check size={12} /> 标记解决
                      </button>
                    </div>
                  )}
                  {t.status === "in_progress" && (
                    <div className="flex gap-2 mt-3">
                      <button
                        onClick={() => updateTicket(t.id, { status: "resolved" })}
                        className="flex items-center gap-1 text-xs px-2 py-1 bg-green-50 text-green-600 rounded hover:bg-green-100 transition-colors"
                      >
                        <Check size={12} /> 标记解决
                      </button>
                    </div>
                  )}
                </div>
              ))}
            </div>
          )}
        </div>
      ) : (
        /* 对话面板 */
        <div className="max-w-2xl bg-white rounded-xl border border-slate-200 flex flex-col h-[600px]">
          <div className="flex-1 overflow-auto p-4 space-y-3">
            {messages.map((msg, i) => (
              <div
                key={i}
                className={`flex ${
                  msg.role === "customer" ? "justify-end" : "justify-start"
                }`}
              >
                <div
                  className={`max-w-[80%] rounded-lg px-4 py-2 text-sm ${
                    msg.role === "customer"
                      ? "bg-blue-600 text-white"
                      : msg.role === "system"
                      ? "bg-red-50 text-red-600"
                      : "bg-slate-100 text-slate-800"
                  }`}
                >
                  {msg.intent && (
                    <span className="block text-xs opacity-60 mb-1">
                      意图: {msg.intent}
                    </span>
                  )}
                  {msg.content}
                  {msg.auto_reply && (
                    <span className="block text-xs opacity-60 mt-1">自动回复</span>
                  )}
                </div>
              </div>
            ))}

            {/* 流式输出中的消息 */}
            {streamingText && (
              <div className="flex justify-start">
                <div className="max-w-[80%] rounded-lg px-4 py-2 text-sm bg-slate-100 text-slate-800">
                  {streamingText}
                  <span className="inline-block w-1.5 h-4 bg-blue-600 ml-0.5 animate-pulse align-middle" />
                </div>
              </div>
            )}

            {/* 加载指示器 */}
            {loading && !streamingText && (
              <div className="flex justify-start">
                <div className="bg-slate-100 rounded-lg px-4 py-2 text-sm text-slate-400">
                  {currentStep ? (
                    <span>{currentStep}...</span>
                  ) : (
                    <div className="flex items-center gap-2">
                      <span className="animate-pulse">●</span>
                      <span className="animate-pulse" style={{ animationDelay: "0.2s" }}>●</span>
                      <span className="animate-pulse" style={{ animationDelay: "0.4s" }}>●</span>
                      Agent 处理中...
                    </div>
                  )}
                </div>
              </div>
            )}

            <div ref={chatEndRef} />
          </div>

          <div className="border-t border-slate-200 p-4">
            <div className="flex gap-2">
              <input
                type="text"
                value={input}
                onChange={(e) => setInput(e.target.value)}
                onKeyDown={(e) => e.key === "Enter" && sendMessage()}
                placeholder="输入消息..."
                disabled={loading}
                className="flex-1 px-3 py-2 border border-slate-300 rounded-lg text-sm focus:ring-2 focus:ring-blue-500 disabled:opacity-50"
              />
              <button
                onClick={toggleVoice}
                disabled={loading}
                className={`px-3 py-2 rounded-lg transition-colors ${
                  isListening
                    ? "bg-red-500 text-white animate-pulse"
                    : "bg-slate-100 text-slate-600 hover:bg-slate-200"
                }`}
                title={isListening ? "停止录音" : "语音输入"}
              >
                {isListening ? <MicOff size={18} /> : <Mic size={18} />}
              </button>
              <button
                onClick={sendMessage}
                disabled={loading || !input.trim()}
                className="bg-blue-600 text-white px-4 py-2 rounded-lg hover:bg-blue-700 transition-colors disabled:opacity-50"
              >
                <Send size={18} />
              </button>
            </div>
          </div>
        </div>
      )}
    </div>
  );
}

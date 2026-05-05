<script setup lang="ts">
import { RouterLink } from "vue-router";
import { ArrowRight, Bot, FileText, MessageSquare, Sparkles, Zap } from "lucide-vue-next";
</script>

<template>
  <div class="landing">
    <!-- Hero -->
    <section class="hero">
      <div class="hero__badge">
        <Sparkles :size="14" /> AI-Powered Video Workflow
      </div>
      <h1 class="hero__title">
        <span class="hero__gradient">VidWise</span>
      </h1>
      <p class="hero__sub">从视频中提取智慧 — 一键转写、智能整理、AI对话</p>
      <p class="hero__desc">
        粘贴抖音/B站链接，自动下载视频、语音转文字、AI格式化，
        还可以和Agent对话深入理解视频内容。
      </p>
      <RouterLink to="/extract" class="hero__cta">
        Try VidWise <ArrowRight :size="18" />
      </RouterLink>
    </section>

    <!-- Features -->
    <section class="features">
      <div class="feature-card">
        <div class="feature-card__icon">
          <FileText :size="22" />
        </div>
        <h3>智能提取</h3>
        <p>粘贴链接即可自动下载视频、提取音频、转写文字、AI格式化排版。</p>
      </div>
      <div class="feature-card">
        <div class="feature-card__icon">
          <MessageSquare :size="22" />
        </div>
        <h3>Agent 对话</h3>
        <p>基于转写内容与AI深度对话，提问、总结、分析，真正理解视频内容。</p>
      </div>
      <div class="feature-card">
        <div class="feature-card__icon">
          <Bot :size="22" />
        </div>
        <h3>多模型支持</h3>
        <p>支持 DeepSeek V4 Pro 和 MiMo V2.5 Pro，选择最适合你的AI引擎。</p>
      </div>
    </section>

    <!-- Footer -->
    <footer class="landing-footer">
      <span>Powered by <strong>VidWise</strong></span>
      <span class="landing-footer__dot">·</span>
      <span>本地引擎 · 隐私安全</span>
    </footer>
  </div>
</template>

<style scoped>
.landing {
  min-height: 100vh;
  display: flex;
  flex-direction: column;
  align-items: center;
  justify-content: center;
  background: linear-gradient(135deg, #0a0a1a 0%, #12122a 30%, #1a1040 60%, #0d0d20 100%);
  color: #e0dff0;
  padding: 60px 24px;
  text-align: center;
}

/* ── Hero ──────────────────────────────────────────────────────── */
.hero {
  max-width: 640px;
  margin-bottom: 80px;
}

.hero__badge {
  display: inline-flex;
  align-items: center;
  gap: 8px;
  padding: 6px 16px;
  border-radius: 999px;
  background: rgba(108, 92, 231, 0.12);
  border: 1px solid rgba(108, 92, 231, 0.25);
  color: #a89ff0;
  font-size: 13px;
  font-weight: 500;
  margin-bottom: 28px;
}

.hero__title {
  margin: 0 0 16px;
  font-size: 72px;
  font-weight: 800;
  letter-spacing: -0.03em;
  line-height: 1.1;
}

.hero__gradient {
  background: linear-gradient(135deg, #6c5ce7 0%, #a855f7 50%, #6366f1 100%);
  -webkit-background-clip: text;
  -webkit-text-fill-color: transparent;
  background-clip: text;
}

.hero__sub {
  margin: 0 0 12px;
  font-size: 20px;
  font-weight: 500;
  color: #c8c4e8;
  letter-spacing: -0.01em;
}

.hero__desc {
  margin: 0 0 36px;
  font-size: 15px;
  color: #8884b0;
  line-height: 1.7;
  max-width: 480px;
  margin-left: auto;
  margin-right: auto;
}

.hero__cta {
  display: inline-flex;
  align-items: center;
  gap: 10px;
  height: 52px;
  padding: 0 32px;
  border-radius: 14px;
  background: linear-gradient(135deg, #6c5ce7 0%, #7c3aed 100%);
  color: #fff;
  font-size: 17px;
  font-weight: 700;
  text-decoration: none;
  transition: box-shadow 0.2s, transform 0.2s;
  box-shadow: 0 4px 24px rgba(108, 92, 231, 0.35);
}

.hero__cta:hover {
  transform: translateY(-2px);
  box-shadow: 0 8px 32px rgba(108, 92, 231, 0.50);
}

/* ── Features ──────────────────────────────────────────────────── */
.features {
  display: grid;
  grid-template-columns: repeat(3, minmax(240px, 300px));
  gap: 20px;
  max-width: 980px;
  margin-bottom: 80px;
}

.feature-card {
  padding: 32px 24px;
  border-radius: 16px;
  background: rgba(255, 255, 255, 0.03);
  border: 1px solid rgba(255, 255, 255, 0.06);
  text-align: center;
  transition: border-color 0.2s, background 0.2s;
}

.feature-card:hover {
  background: rgba(255, 255, 255, 0.05);
  border-color: rgba(108, 92, 231, 0.25);
}

.feature-card__icon {
  display: inline-flex;
  align-items: center;
  justify-content: center;
  width: 48px;
  height: 48px;
  border-radius: 12px;
  background: rgba(108, 92, 231, 0.12);
  color: #a89ff0;
  margin-bottom: 16px;
}

.feature-card h3 {
  margin: 0 0 8px;
  font-size: 17px;
  font-weight: 700;
  color: #e0dff0;
}

.feature-card p {
  margin: 0;
  font-size: 13px;
  color: #8884b0;
  line-height: 1.6;
}

/* ── Footer ────────────────────────────────────────────────────── */
.landing-footer {
  color: #5c5880;
  font-size: 13px;
  display: flex;
  gap: 8px;
}

.landing-footer strong {
  color: #8884b0;
}

.landing-footer__dot {
  color: #3c3870;
}

@media (max-width: 768px) {
  .hero__title { font-size: 48px; }
  .features { grid-template-columns: 1fr; max-width: 400px; }
}
</style>

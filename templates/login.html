<!DOCTYPE html>
<html lang="pt-BR">
<head>
  <meta charset="UTF-8" />
  <meta name="viewport" content="width=device-width, initial-scale=1.0"/>
  <title>VoltaCliente Conchal - Acesso</title>

  <link rel="manifest" href="/static/manifest.json"/>
  <meta name="theme-color" content="#10b981"/>
  <meta name="mobile-web-app-capable" content="yes"/>
  <meta name="apple-mobile-web-app-capable" content="yes"/>
  <meta name="apple-mobile-web-app-title" content="VoltaCliente"/>
  <link rel="apple-touch-icon" href="/static/icon-192.png"/>

  <script src="https://cdn.tailwindcss.com"></script>
  <link href="https://fonts.googleapis.com/css2?family=Syne:wght@600;700;800&family=Inter:wght@300;400;500;600&display=swap" rel="stylesheet"/>
  <style>
    * { font-family: 'Inter', sans-serif; }
    .brand { font-family: 'Syne', sans-serif; }
    body { background:#0f172a; color:#e2e8f0; }
    .card { background:rgba(255,255,255,0.04); border:1px solid rgba(255,255,255,0.08); }
    .input-field { background:rgba(255,255,255,0.06); border:1px solid rgba(255,255,255,0.1); color:#f1f5f9; }
    .input-field:focus { outline:none; border-color:#10b981; box-shadow:0 0 0 3px rgba(16,185,129,0.15); }
    .btn-primary { background:linear-gradient(135deg,#10b981,#059669); }
    .btn-mp { background:linear-gradient(135deg,#009ee3,#0070b9); }
  </style>
</head>
<body class="min-h-screen p-4 flex items-center justify-center">
  <main class="w-full max-w-5xl grid lg:grid-cols-[0.9fr_1.1fr] gap-5">
    <section class="card rounded-2xl p-6 lg:p-8 flex flex-col justify-between">
      <div>
        <div class="flex items-center gap-3 mb-8">
          <div class="w-11 h-11 rounded-xl bg-emerald-500 flex items-center justify-center text-xl">VC</div>
          <div>
            <h1 class="brand text-2xl font-800 text-white">VoltaCliente Conchal</h1>
            <p class="text-slate-400 text-sm">Retencao via WhatsApp para comercios locais</p>
          </div>
        </div>

        <div class="rounded-2xl border border-emerald-500/20 bg-emerald-500/10 p-4 mb-5">
          <p class="text-emerald-300 text-sm font-semibold">Teste livre sem login</p>
          <p class="text-slate-300 text-sm mt-1">
            Use o sistema por 10 minutos. Depois crie sua conta e libere 7 dias gratis.
          </p>
          <div class="mt-4 inline-flex items-center gap-2 rounded-xl bg-slate-950/60 px-3 py-2 text-sm">
            Tempo restante: <span id="timer" class="font-semibold text-emerald-300">--:--</span>
          </div>
        </div>

        <a href="/dashboard" class="btn-primary block text-center rounded-xl py-3 font-semibold text-white">
          Entrar na degustacao agora
        </a>
      </div>

      <div class="mt-6 text-xs text-slate-500">
        Plano premium apos o trial: R$ 30,00 por mes via Mercado Pago.
      </div>
    </section>

    <section class="grid md:grid-cols-2 gap-5">
      <div class="card rounded-2xl p-6">
        <h2 class="brand text-xl font-700 text-white mb-2">Criar conta</h2>
        <p class="text-slate-400 text-sm mb-5">Ganhe 7 dias gratis automaticamente.</p>

        {% for msg in get_flashed_messages(category_filter=["sucesso"]) %}
        <div class="bg-emerald-500/10 border border-emerald-500/30 text-emerald-300 text-sm rounded-xl p-3 mb-4">{{ msg }}</div>
        {% endfor %}
        {% for msg in get_flashed_messages(category_filter=["erro"]) %}
        <div class="bg-red-500/10 border border-red-500/30 text-red-300 text-sm rounded-xl p-3 mb-4">{{ msg }}</div>
        {% endfor %}

        <form method="POST" action="/registrar" class="space-y-3">
          <input name="nome" class="input-field w-full rounded-xl px-4 py-3 text-sm" placeholder="Seu nome" required>
          <input name="nome_comercio" class="input-field w-full rounded-xl px-4 py-3 text-sm" placeholder="Nome do estabelecimento">
          <input type="email" name="email" class="input-field w-full rounded-xl px-4 py-3 text-sm" placeholder="E-mail" required>
          <input type="password" name="senha" class="input-field w-full rounded-xl px-4 py-3 text-sm" placeholder="Criar senha" required>
          <button class="btn-primary w-full rounded-xl py-3 font-semibold text-white">Criar e liberar 7 dias</button>
        </form>
      </div>

      <div class="card rounded-2xl p-6">
        <h2 class="brand text-xl font-700 text-white mb-2">Ja tenho conta</h2>
        <p class="text-slate-400 text-sm mb-5">Entre para continuar usando.</p>

        <form method="POST" action="/login" class="space-y-3">
          <input type="email" name="email" class="input-field w-full rounded-xl px-4 py-3 text-sm" placeholder="E-mail" required>
          <input type="password" name="senha" class="input-field w-full rounded-xl px-4 py-3 text-sm" placeholder="Senha" required>
          <button class="btn-primary w-full rounded-xl py-3 font-semibold text-white">Entrar</button>
        </form>

        <div class="mt-5 rounded-2xl border border-white/10 p-4">
          <p class="text-slate-300 text-sm font-semibold">Premium mensal</p>
          <p class="text-slate-500 text-sm mt-1">Depois dos 7 dias gratis, continue por R$ 30,00/mes.</p>
          <a href="{{ checkout_url }}" target="_blank" class="btn-mp mt-4 block text-center rounded-xl py-3 font-semibold text-white">
            Pagar com Mercado Pago
          </a>
        </div>
      </div>
    </section>
  </main>

  <script>
    let restante = Number("{{ demo_seconds_remaining|default(0) }}");
    const timer = document.getElementById("timer");

    function renderTimer() {
      const min = String(Math.floor(restante / 60)).padStart(2, "0");
      const sec = String(restante % 60).padStart(2, "0");
      timer.textContent = `${min}:${sec}`;
      if (restante > 0) restante -= 1;
    }

    renderTimer();
    setInterval(renderTimer, 1000);

    if ("serviceWorker" in navigator) {
      navigator.serviceWorker.register("/static/service-worker.js").catch(() => {});
    }
  </script>
</body>
</html>

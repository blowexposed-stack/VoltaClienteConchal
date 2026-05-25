<!DOCTYPE html>
<html lang="pt-BR">
<head>
  <meta charset="UTF-8"/>
  <meta name="viewport" content="width=device-width, initial-scale=1.0"/>
  <title>Agendar - {{ usuario.nome_comercio }}</title>
  <meta name="theme-color" content="#10b981"/>
  <script src="https://cdn.tailwindcss.com"></script>
  <link href="https://fonts.googleapis.com/css2?family=Syne:wght@700;800&family=Inter:wght@400;500;600&display=swap" rel="stylesheet"/>
  <style>
    * { font-family:'Inter', sans-serif; }
    .brand { font-family:'Syne', sans-serif; }
    body { background:#0f172a; color:#e2e8f0; }
    .card { background:rgba(255,255,255,0.04); border:1px solid rgba(255,255,255,0.08); }
    .input-field { background:rgba(255,255,255,0.06); border:1px solid rgba(255,255,255,0.1); color:#f1f5f9; }
    .input-field:focus { outline:none; border-color:#10b981; box-shadow:0 0 0 3px rgba(16,185,129,0.15); }
    .btn-primary { background:linear-gradient(135deg,#10b981,#059669); }
  </style>
</head>
<body class="min-h-screen p-4">
  <main class="max-w-lg mx-auto py-6">
    <header class="mb-6">
      <div class="w-12 h-12 rounded-2xl bg-emerald-500 flex items-center justify-center font-bold text-white mb-4">VC</div>
      <h1 class="brand text-3xl font-800 text-white">{{ usuario.nome_comercio }}</h1>
      <p class="text-slate-400 text-sm mt-2">Escolha um horario disponivel e confirme seu atendimento.</p>
    </header>

    {% for msg in get_flashed_messages(category_filter=["sucesso"]) %}
    <div class="bg-emerald-500/10 border border-emerald-500/30 text-emerald-300 text-sm rounded-xl p-3 mb-4">{{ msg }}</div>
    {% endfor %}
    {% for msg in get_flashed_messages(category_filter=["erro"]) %}
    <div class="bg-red-500/10 border border-red-500/30 text-red-300 text-sm rounded-xl p-3 mb-4">{{ msg }}</div>
    {% endfor %}

    <section class="card rounded-2xl p-5">
      <form method="POST" class="space-y-4">
        <div>
          <label class="block text-slate-400 text-xs uppercase tracking-wider font-600 mb-2">Seu nome</label>
          <input name="nome" class="input-field w-full rounded-xl px-4 py-3 text-sm" placeholder="Ex: Pamela" required>
        </div>
        <div>
          <label class="block text-slate-400 text-xs uppercase tracking-wider font-600 mb-2">Seu WhatsApp</label>
          <input name="celular" class="input-field w-full rounded-xl px-4 py-3 text-sm" placeholder="Ex: 19 99999-0000" required>
        </div>
        <div>
          <label class="block text-slate-400 text-xs uppercase tracking-wider font-600 mb-2">Servico desejado</label>
          <input name="servico" class="input-field w-full rounded-xl px-4 py-3 text-sm" placeholder="Ex: mao e pe, unhas bonitas">
        </div>
        <div>
          <label class="block text-slate-400 text-xs uppercase tracking-wider font-600 mb-2">Horario</label>
          <select name="horario_id" class="input-field w-full rounded-xl px-4 py-3 text-sm" required>
            <option value="">Selecione...</option>
            {% for h in horarios %}
            <option value="{{ h.id }}">{{ h.data }} as {{ h.hora_inicio }}</option>
            {% endfor %}
          </select>
        </div>
        <button class="btn-primary w-full rounded-xl py-3 font-semibold text-white">Confirmar agendamento</button>
      </form>

      {% if not horarios %}
      <p class="text-slate-500 text-sm mt-4 text-center">Nenhum horario livre no momento. Entre em contato diretamente.</p>
      {% endif %}
    </section>

    <p class="text-center text-xs text-slate-600 mt-6">Powered by VoltaCliente Conchal</p>
  </main>
</body>
</html>

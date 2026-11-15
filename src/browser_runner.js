// Runs model jobs from the OpenRouter tab (https://openrouter.ai origin). Injected by the operator.
// Usage: await AB.load(jobsUrl, {lineup: url, toddlers: url}); AB.start(concurrency); AB.status(); AB.take()
window.AB = window.AB || {};
Object.assign(window.AB, {
  jobs: [], queue: [], results: {}, taken: new Set(), running: 0, imgs: {}, log: [],
  async load(jobsUrl, imgUrls) {
    const jobs = await (await fetch(jobsUrl)).json();
    for (const [k, u] of Object.entries(imgUrls)) {
      if (this.imgs[k]) continue;
      const b = await (await fetch(u)).blob();
      this.imgs[k] = await new Promise(res => { const fr = new FileReader(); fr.onload = () => res(fr.result); fr.readAsDataURL(b); });
    }
    this.jobs.push(...jobs); this.queue.push(...jobs.filter(j => !this.results[j.id]));
    return {loaded: jobs.length, queued: this.queue.length, imgs: Object.keys(this.imgs)};
  },
  async call(job) {
    const key = localStorage.getItem('ab_key');
    const msgs = job.messages || [{role: 'user', content: [
      {type: 'text', text: job.prompt},
      {type: 'image_url', image_url: {url: this.imgs[job.image]}}]}];
    const t0 = Date.now();
    const body = {model: job.model, messages: msgs, max_tokens: 32000, usage: {include: true}};
    for (let attempt = 1; attempt <= 3; attempt++) {
      try {
        const r = await fetch('https://openrouter.ai/api/v1/chat/completions', {method: 'POST',
          headers: {'Authorization': 'Bearer ' + key, 'Content-Type': 'application/json',
                    'HTTP-Referer': 'https://github.com/floflo11/anibench', 'X-Title': 'anibench'},
          body: JSON.stringify(body)});
        const j = await r.json();
        if (!r.ok || j.error) throw new Error((j.error && (j.error.message || JSON.stringify(j.error))) || ('HTTP ' + r.status));
        const c = j.choices && j.choices[0];
        return {id: job.id, stage: job.stage || 'first', model: job.model, provider: j.provider,
                content: c && c.message && c.message.content, finish: c && c.finish_reason,
                usage: j.usage, latency_s: (Date.now() - t0) / 1000, attempts: attempt};
      } catch (e) {
        if (attempt === 3) return {id: job.id, stage: job.stage || 'first', model: job.model, error: String(e).slice(0, 500), latency_s: (Date.now() - t0) / 1000};
        await new Promise(res => setTimeout(res, 5000 * attempt));
      }
    }
  },
  start(concurrency = 8) {
    const pump = () => {
      while (this.running < concurrency && this.queue.length) {
        const job = this.queue.shift(); this.running++;
        this.call(job).then(r => { this.results[r.id + '@' + r.stage] = r; }).finally(() => { this.running--; pump(); });
      }
    };
    pump(); return this.status();
  },
  status() {
    const rs = Object.values(this.results);
    const cost = rs.reduce((a, r) => a + ((r.usage && r.usage.cost) || 0), 0);
    return {done: rs.length, errors: rs.filter(r => r.error).length, running: this.running, queued: this.queue.length,
            untaken: rs.filter(r => !this.taken.has(r.id + '@' + r.stage)).length, cost_usd: Math.round(cost * 100) / 100};
  },
  take(max = 60) {
    const out = {};
    for (const [k, r] of Object.entries(this.results)) {
      if (this.taken.has(k)) continue; out[k] = r; this.taken.add(k); if (Object.keys(out).length >= max) break;
    }
    return JSON.stringify({results: out});
  },
});
'AB ready'

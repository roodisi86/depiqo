(function () {
  "use strict";
  var root = document.documentElement;
  root.classList.add("js");

  // Header: subtle border once the page scrolls
  var header = document.querySelector("[data-header]");
  if (header) {
    var onScroll = function () { header.classList.toggle("scrolled", window.scrollY > 8); };
    window.addEventListener("scroll", onScroll, { passive: true });
    onScroll();
  }

  // Mega menu (a <details>): close with Escape, on outside click and after choosing a link
  var megas = Array.prototype.slice.call(document.querySelectorAll("details[data-mega], details.menu"));
  megas.forEach(function (d) {
    d.addEventListener("toggle", function () {
      if (d.open) megas.forEach(function (o) { if (o !== d) o.open = false; });
    });
  });
  document.addEventListener("keydown", function (e) {
    if (e.key !== "Escape") return;
    megas.forEach(function (d) {
      if (d.open) { d.open = false; var s = d.querySelector("summary"); if (s) s.focus(); }
    });
  });
  document.addEventListener("click", function (e) {
    megas.forEach(function (d) { if (d.open && !d.contains(e.target)) d.open = false; });
  });
  document.querySelectorAll("details[data-mega] a, details.menu a").forEach(function (a) {
    a.addEventListener("click", function () { megas.forEach(function (d) { d.open = false; }); });
  });

  // Gentle reveal on scroll; everything is visible without JS or with reduced motion
  var reveals = document.querySelectorAll(".reveal");
  var reduce = window.matchMedia && window.matchMedia("(prefers-reduced-motion: reduce)").matches;
  if (!("IntersectionObserver" in window) || reduce) {
    reveals.forEach(function (el) { el.classList.add("in"); });
  } else {
    var io = new IntersectionObserver(function (entries) {
      entries.forEach(function (en) { if (en.isIntersecting) { en.target.classList.add("in"); io.unobserve(en.target); } });
    }, { rootMargin: "0px 0px -8% 0px" });
    reveals.forEach(function (el) { io.observe(el); });
  }

  var numOf = function (id) {
    var el = document.getElementById(id);
    if (!el) return 0;
    var v = Number(String(el.value).replace(/\./g, "").replace(",", "."));
    return isFinite(v) && v > 0 ? v : 0;
  };
  var eur = function (x, dec) {
    return "€ " + x.toLocaleString("nl-NL", { minimumFractionDigits: dec || 0, maximumFractionDigits: dec || 0 });
  };

  // Time calculator (vastgoedbeheerders)
  var calc = document.querySelector("[data-calc]");
  if (calc) {
    var fmt = function (x) { return Math.round(x).toLocaleString("nl-NL"); };
    var update = function () {
      var before = (numOf("c-new") * numOf("c-min-new") + numOf("c-end") * numOf("c-min-end")) / 60;
      var pct = Math.min(numOf("c-pct"), 100);
      var saved = before * pct / 100;
      document.getElementById("r-before").textContent = fmt(before) + " uur";
      document.getElementById("r-saved").textContent = fmt(saved) + " uur";
      document.getElementById("r-fte").textContent = (saved / 1600).toLocaleString("nl-NL", { maximumFractionDigits: 2, minimumFractionDigits: 2 }) + " fte";
      document.getElementById("r-days").textContent = fmt(saved / 8);
    };
    calc.addEventListener("input", update);
    update();
  }

  // Price calculator: same rules as the platform's billing (included dossiers go to "elsewhere" first)
  var pc = document.querySelector("[data-price-calc]");
  if (pc) {
    var plans = JSON.parse(pc.getAttribute("data-plans"));
    var dec = function (s) { return Number(String(s).replace(",", ".")); };
    var priceOf = function (p, active, share, fresh) {
      var depiqo = Math.round(active * share / 100), ext = active - depiqo;
      var incl = p.included;
      var extIncl = Math.min(ext, incl), dpqIncl = Math.min(depiqo, incl - extIncl);
      var extExtra = ext - extIncl, dpqExtra = depiqo - dpqIncl;
      var total = p.base + extExtra * dec(p.ext) + dpqExtra * dec(p.dpq) + fresh * dec(p["new"]);
      return { total: total, ext: ext, depiqo: depiqo, extExtra: extExtra, dpqExtra: dpqExtra };
    };
    var updateP = function () {
      var active = Math.round(numOf("p-active")), share = Math.min(numOf("p-share"), 100), fresh = Math.round(numOf("p-new"));
      var best = null;
      plans.forEach(function (p) {
        var r = priceOf(p, active, share, fresh);
        p._r = r;
        document.getElementById("p-" + p.key).textContent = eur(r.total, 2);
        if (!best || r.total < best._r.total) best = p;
      });
      document.querySelectorAll("[data-plan-line]").forEach(function (l) { l.classList.toggle("best", l.getAttribute("data-plan-line") === best.key); });
      var r = best._r;
      document.getElementById("p-best").textContent = best.name + ": " + eur(r.total, 0);
      document.getElementById("p-per").textContent = active ? eur(r.total / active, 2) : "—";
      var parts = [eur(best.base) + " basis", best.included + " dossiers inbegrepen (eerst de dossiers elders)"];
      if (r.extExtra) parts.push(r.extExtra + " extra elders à € " + best.ext);
      if (r.dpqExtra) parts.push(r.dpqExtra + " extra op een Depiqo-borgrekening à € " + best.dpq);
      if (fresh) parts.push(fresh + " nieuwe dossiers à € " + best["new"]);
      document.getElementById("p-explain").textContent = best.name + ": " + parts.join(", ") + ". Excl. btw. Huurders betalen niets.";
    };
    pc.addEventListener("input", updateP);
    updateP();
  }

  // Lead forms (Netlify Forms)
  var preview = document.body.getAttribute("data-preview") === "1";
  document.querySelectorAll("form[data-lead]").forEach(function (form) {
    var status = form.querySelector(".form-status");
    form.addEventListener("submit", function (e) {
      e.preventDefault();
      var ok = true;
      form.querySelectorAll("[data-required]").forEach(function (el) {
        var err = document.getElementById(el.id + "-err");
        var bad = el.type === "checkbox" ? !el.checked : !String(el.value).trim();
        if (!bad && el.type === "email") bad = !/^[^\s@]+@[^\s@]+\.[^\s@]+$/.test(el.value);
        el.setAttribute("aria-invalid", bad ? "true" : "false");
        if (err) err.textContent = bad ? el.getAttribute("data-error") : "";
        if (bad && ok) { el.focus(); ok = false; }
      });
      if (!ok) return;
      if (preview) {
        status.hidden = false;
        status.className = "form-status warn";
        status.textContent = "Dit is een preview. Het formulier is gecontroleerd, maar er is niets verstuurd.";
        return;
      }
      var body = new URLSearchParams(new FormData(form)).toString();
      fetch("/", { method: "POST", headers: { "Content-Type": "application/x-www-form-urlencoded" }, body: body })
        .then(function (r) {
          if (!r.ok) throw new Error(r.status);
          form.reset();
          status.hidden = false;
          status.className = "form-status ok";
          status.textContent = "Bedankt. We nemen binnen twee werkdagen contact met je op.";
        })
        .catch(function () {
          status.hidden = false;
          status.className = "form-status warn";
          status.textContent = "Versturen is niet gelukt. Probeer het opnieuw of mail naar hallo@getdepiqo.com.";
        });
    });
  });
})();

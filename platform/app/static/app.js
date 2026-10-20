(function () {
  "use strict";
  // Ask before irreversible actions
  document.querySelectorAll("form[data-confirm]").forEach(function (f) {
    f.addEventListener("submit", function (e) { if (!window.confirm(f.getAttribute("data-confirm"))) e.preventDefault(); });
  });
  // Selects that submit their form
  document.querySelectorAll("select.auto-submit").forEach(function (s) {
    s.addEventListener("change", function () { s.form.submit(); });
  });
  // Settlement: reveal another line
  document.querySelectorAll("[data-add-line]").forEach(function (b) {
    b.addEventListener("click", function () {
      var next = b.closest("form").querySelector("[data-line][hidden]");
      if (next) { next.hidden = false; next.querySelector("input").focus(); }
      if (!b.closest("form").querySelector("[data-line][hidden]")) b.disabled = true;
    });
  });
  // New deposit: hide address when an existing property is chosen
  var nd = document.getElementById("new-deposit");
  if (nd) {
    var prop = document.getElementById("property_id"),
        newProp = document.getElementById("new-property"), region = document.getElementById("region");
    var sync = function () {
      if (prop) {
        var opt = prop.options[prop.selectedIndex];
        newProp.hidden = !!prop.value;
        if (prop.value && opt.getAttribute("data-region")) { region.value = opt.getAttribute("data-region"); region.disabled = true; }
        else { region.disabled = false; }
      }
      document.getElementById("rent-hint").textContent = region.value === "NL" ? "In Nederland de kale huur, zonder servicekosten." :
        (region.value === "BRU" ? "In Brussel de huur zonder lasten." : "De maandhuur.");
    };
    nd.addEventListener("change", sync);
    nd.addEventListener("submit", function () { region.disabled = false; });
    sync();
  }
  // Provider of a deposit held elsewhere: fields per kind and a region warning (never blocking)
  document.querySelectorAll("[data-provider-form]").forEach(function (form) {
    var kind = form.querySelector("select[name=provider_kind]");
    if (!kind) return;
    var box = form.querySelector("[data-provider-box]"), warn = form.querySelector("[data-provider-warning]"),
        iban = form.querySelector("[data-iban-field]"), expiry = form.querySelector("[data-expiry-field]"),
        refLabel = form.querySelector("[data-ref-label-target]"), regionSel = form.querySelector("#region");
    var sync = function () {
      var holding = form.querySelector("input[name=holding]:checked");
      var external = !holding || holding.value === "external";
      var opt = kind.options[kind.selectedIndex];
      var region = regionSel ? regionSel.value : (form.getAttribute("data-region") || "");
      if (box) box.hidden = !external;
      var text = external && opt ? (opt.getAttribute("data-warn-" + region.toLowerCase()) || "") : "";
      if (warn) { warn.textContent = text; warn.hidden = !text; }
      if (iban) iban.hidden = !external || (opt && opt.getAttribute("data-no-payment") === "1");
      if (expiry) expiry.hidden = !external || !(opt && opt.getAttribute("data-guarantee") === "1");
      if (refLabel && opt) refLabel.textContent = opt.getAttribute("data-ref-label") + " (optioneel)";
    };
    form.addEventListener("change", sync);
    sync();
  });
  // Deposits list: select rows for bulk actions
  var bulk = document.getElementById("bulk-form");
  if (bulk) {
    var all = bulk.querySelector("[data-pick-all]"), picks = bulk.querySelectorAll("[data-pick]"),
        counter = bulk.querySelector("[data-selected-count]"), buttons = bulk.querySelectorAll("[data-needs-selection]");
    var update = function () {
      var n = 0;
      picks.forEach(function (c) { if (c.checked) n++; });
      if (counter) counter.textContent = n;
      buttons.forEach(function (b) { b.disabled = n === 0; });
      if (all) { all.checked = n > 0 && n === picks.length; all.indeterminate = n > 0 && n < picks.length; }
    };
    if (all) all.addEventListener("change", function () { picks.forEach(function (c) { c.checked = all.checked; }); update(); });
    picks.forEach(function (c) { c.addEventListener("change", update); });
    update();
  }
  // Outbox: make URLs clickable without injecting HTML
  document.querySelectorAll("[data-linkify]").forEach(function (pre) {
    var text = pre.textContent, re = /(https?:\/\/[^\s]+)/g, last = 0, m, frag = document.createDocumentFragment();
    while ((m = re.exec(text))) {
      frag.appendChild(document.createTextNode(text.slice(last, m.index)));
      var a = document.createElement("a"); a.href = m[1]; a.textContent = m[1]; frag.appendChild(a);
      last = m.index + m[1].length;
    }
    frag.appendChild(document.createTextNode(text.slice(last)));
    pre.textContent = ""; pre.appendChild(frag);
  });
})();

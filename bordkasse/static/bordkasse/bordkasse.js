/* Bordkasse & Einkaufsliste — UI aus dem Claude-Artifact-Prototyp, Daten über die Django-JSON-API.
   Jede schreibende Anfrage liefert den kompletten neuen Zustand zurück; zusätzlich wird alle 20 s
   nachgeladen, damit die Crew Änderungen der anderen sieht. */
(function(){
  "use strict";

  var CFG = window.BORDKASSE_CONFIG;
  var CASH = 'Bordkasse (Bargeld)';
  var POLL_MS = 20000;

  var fmt = new Intl.NumberFormat('de-DE',{style:'currency',currency:'EUR'});
  function money(n){ return fmt.format(Math.round((n||0)*100)/100); }
  function esc(s){
    return (s==null ? '' : String(s)).replace(/[&<>"']/g, function(c){
      return {'&':'&amp;','<':'&lt;','>':'&gt;','"':'&quot;',"'":'&#39;'}[c];
    });
  }
  function $(id){ return document.getElementById(id); }
  function ts(iso){ return iso ? Date.parse(iso) : 0; }

  var state = JSON.parse($('bk-state').textContent);
  var editingTxId = null, expandedShopId = null, editingCrewId = null;
  var kind = 'ausgabe', method = 'karte';

  // ---------- API ----------
  function api(path, body){
    return fetch(CFG.apiBase + path, {
      method: body === undefined ? 'GET' : 'POST',
      headers: {'Content-Type':'application/json', 'X-CSRFToken': CFG.csrfToken},
      credentials: 'same-origin',
      body: body === undefined ? undefined : JSON.stringify(body)
    }).then(function(r){
      return r.json().catch(function(){ return {}; }).then(function(data){
        if (!r.ok){ var e = new Error(data.error || 'Fehler beim Speichern.'); e.status = r.status; throw e; }
        state = data;
        setBanner('');
        render();
        return data;
      });
    });
  }
  function handleError(e){
    console.error(e);
    setBanner(esc(e.message || 'Fehler beim Speichern.') +
      (e.status===403 ? ' <a href="/accounts/login/?next='+encodeURIComponent(location.pathname)+'">Anmelden</a>' : ''), true);
  }

  // ---------- tabs ----------
  function setTab(name){
    document.querySelectorAll('.tab').forEach(function(b){ b.classList.toggle('active', b.dataset.tab===name); });
    document.querySelectorAll('.panel').forEach(function(p){ p.classList.toggle('active', p.id==='panel-'+name); });
    if (location.hash !== '#'+name) history.replaceState(null,'','#'+name);
  }
  document.querySelectorAll('.tab').forEach(function(b){ b.addEventListener('click', function(){ setTab(b.dataset.tab); }); });
  setTab(['liste','historie'].indexOf(location.hash.slice(1))>=0 ? location.hash.slice(1) : 'kasse');

  // ---------- banner ----------
  function setBanner(html, warn){
    $('statusbanner').innerHTML = html ? '<div class="banner'+(warn?' warn':'')+'">'+html+'</div>' : '';
  }

  // ---------- read-only mode for the Bordkasse (Einkaufsliste is open to everyone) ----------
  function applyWriteMode(){
    document.querySelectorAll('[data-write]').forEach(function(el){ el.hidden = !state.can_write; });
  }

  // ---------- segmented controls ----------
  $('kindctl').addEventListener('click', function(ev){
    var b = ev.target.closest('button[data-kind]');
    if (!b) return;
    kind = b.dataset.kind;
    document.querySelectorAll('#kindctl button').forEach(function(x){ x.classList.toggle('on', x===b); });
    $('personlabel').textContent = kind==='einzahlung' ? 'Eingezahlt von' : 'Bezahlt von';
    renderPersonOptions();
  });
  $('methodctl').addEventListener('click', function(ev){
    var b = ev.target.closest('button[data-method]');
    if (!b) return;
    method = b.dataset.method;
    document.querySelectorAll('#methodctl button').forEach(function(x){ x.classList.toggle('on', x===b); });
  });
  $('personsel').addEventListener('change', updateMethodRow);

  function updateMethodRow(){
    var v = $('personsel').value;
    $('methodrow').hidden = !(kind==='ausgabe' && v && v!=='kasse');
  }

  function personOptionsHtml(forKind, selected){
    var opts = forKind==='ausgabe' ? [{id:'kasse', name:CASH}] : [];
    opts = opts.concat(state.crew.map(function(c){ return {id:String(c.id), name:c.name}; }));
    return opts.map(function(o){
      return '<option value="'+esc(o.id)+'"'+(o.id===selected?' selected':'')+'>'+esc(o.name)+'</option>';
    }).join('');
  }

  function renderPersonOptions(){
    var sel = $('personsel');
    var prev = sel.value;
    var html = personOptionsHtml(kind, prev);
    sel.innerHTML = html || '<option value="">Erst Crew hinzufügen</option>';
    updateMethodRow();
  }

  // ---------- render ----------
  function render(){
    var t = state.totals;
    $('kassenstand').textContent = money(t.kassenstand);
    $('sumEinBar').textContent = money(t.sum_ein_bar);
    $('sumAusBar').textContent = money(t.sum_aus_bar);
    $('sumEinKarte').textContent = money(t.sum_ein_karte);
    $('sumAusKarte').textContent = money(t.sum_aus_karte);
    $('crewCount').textContent = state.crew.length;
    $('fairShare').textContent = money(t.fair_share);
    applyWriteMode();

    // Während eines Inline-Edits nicht neu aufbauen, sonst gehen Eingaben verloren.
    if (!editingCrewId){
      $('crewgrid').innerHTML = state.crew.length ? state.crew.map(crewCardHtml).join('') :
        '<div class="empty" style="grid-column:1/-1">Noch keine Crew'+(state.can_write?' – unten Namen hinzufügen.':'.')+'</div>';
    }
    renderPersonOptions();

    var visibleTx = state.tx.filter(function(x){ return !x.deleted; });
    $('txhint').textContent = visibleTx.length ? visibleTx.length + ' Einträge' : '';
    if (!editingTxId){
      $('ledgerwrap').innerHTML = visibleTx.length ?
        '<div class="ledger">'+visibleTx.map(txRow).join('')+'</div>' :
        '<div class="empty">Noch keine Einträge.'+(state.can_write?' Trag oben die erste Ausgabe oder Einzahlung ein.':'')+'</div>';
    }

    renderHistory();

    var openItems = state.shop.filter(function(s){ return !s.done; });
    var doneItems = state.shop.filter(function(s){ return s.done; });
    $('shopcount').textContent = openItems.length;
    if (!expandedShopId){
      $('shopopen').innerHTML = openItems.length ? openItems.map(shopRow).join('') :
        '<div class="empty">Liste ist leer – alles besorgt oder noch nichts eingetragen.</div>';
      $('shopdone').innerHTML = doneItems.length ? doneItems.map(shopRow).join('') :
        '<div class="empty">Noch nichts abgehakt.</div>';
    }
  }

  // ---------- crew ----------
  function crewCardHtml(c){
    if (c.id === editingCrewId) return crewCardEditHtml(c);
    var cls = c.saldo >= 0 ? 'pos' : 'neg';
    return '<div class="crewcard" data-id="'+c.id+'">'+
      (state.can_write ? '<button class="crewedit" data-edit-crew="'+c.id+'" title="Umbenennen">✎</button>' : '')+
      '<div class="name">'+esc(c.name)+'</div>'+
      '<div class="saldo '+cls+'">'+(c.saldo>=0?'+':'')+money(c.saldo)+'</div>'+
      '<div class="detail">eingebracht '+money(c.eingebracht)+'</div></div>';
  }
  function crewCardEditHtml(c){
    return '<div class="crewcard editing" data-id="'+c.id+'">'+
      '<input class="crewrename" maxlength="40" value="'+esc(c.name)+'">'+
      '<div class="row">'+
        '<button class="btn primary small" data-save-crew="'+c.id+'" style="flex:none">Speichern</button>'+
        '<button class="btn ghost small" data-cancel-crew="'+c.id+'" style="flex:none">Abbrechen</button>'+
      '</div>'+
      '<div class="crewhint">Bisherige Buchungen werden mit umbenannt.</div></div>';
  }
  function findById(list, id){ return list.find(function(x){ return String(x.id)===String(id); }); }

  // ---------- ledger ----------
  function payTag(t){
    if (t.kind!=='ausgabe' || t.person_id==null) return '';
    return t.method==='bar' ? '💶 Bar (privat) · ' : '💳 Karte · ';
  }
  function txRow(t){
    if (t.id === editingTxId) return txEditRowHtml(t);
    var isEin = t.kind==='einzahlung';
    var d = t.created_at ? new Date(t.created_at).toLocaleDateString('de-DE',{day:'2-digit',month:'2-digit'}) : '';
    var edited = t.revisions.length ? ' · bearbeitet' : '';
    return '<div class="entry '+(isEin?'ein':'aus')+'" data-id="'+t.id+'">'+
      '<div class="who"><div class="p">'+esc(t.person)+'</div>'+
      '<div class="n">'+(d?d+' · ':'')+payTag(t)+(t.note?esc(t.note):(isEin?'Einzahlung':'Ausgabe'))+edited+'</div></div>'+
      '<div class="amt '+(isEin?'ein':'aus')+'">'+(isEin?'+':'–')+money(t.amount)+'</div>'+
      (state.can_write ?
        '<div class="entryactions">'+
          '<button class="iconbtn" data-edit-tx="'+t.id+'" title="Bearbeiten">✎</button>'+
          '<button class="del" data-del-tx="'+t.id+'" title="Löschen">✕</button>'+
        '</div>' : '')+
      '</div>';
  }
  function txEditRowHtml(t){
    var isEin = t.kind==='einzahlung';
    var sel = t.person_id==null ? 'kasse' : String(t.person_id);
    return '<div class="entry editing" data-id="'+t.id+'">'+
      '<div class="editform">'+
        '<div class="row">'+
          '<select class="editkind" style="flex:1 1 120px">'+
            '<option value="ausgabe"'+(!isEin?' selected':'')+'>Ausgabe</option>'+
            '<option value="einzahlung"'+(isEin?' selected':'')+'>Einzahlung</option>'+
          '</select>'+
          '<select class="editperson" style="flex:2 1 160px">'+personOptionsHtml(t.kind, sel)+'</select>'+
        '</div>'+
        '<div class="row">'+
          '<input class="editamount" type="number" inputmode="decimal" min="0.01" step="0.01" value="'+esc(t.amount)+'" style="flex:1 1 100px">'+
          '<select class="editmethod" style="flex:1 1 130px"'+(isEin||sel==='kasse'?' hidden':'')+'>'+
            '<option value="karte"'+(t.method!=='bar'?' selected':'')+'>Karte</option>'+
            '<option value="bar"'+(t.method==='bar'?' selected':'')+'>Bar (privat)</option>'+
          '</select>'+
        '</div>'+
        '<input class="editnote" placeholder="Notiz (optional)" maxlength="80" value="'+esc(t.note)+'" style="margin-bottom:10px">'+
        '<div class="row" style="margin-bottom:0">'+
          '<button class="btn primary small" data-save-edit="'+t.id+'" style="flex:none">Speichern</button>'+
          '<button class="btn ghost small" data-cancel-edit="'+t.id+'" style="flex:none">Abbrechen</button>'+
        '</div>'+
      '</div></div>';
  }
  // Im Edit-Formular Personenliste und Zahlart passend zur gewählten Art umschalten.
  $('ledgerwrap').addEventListener('change', function(ev){
    var form = ev.target.closest('.editform');
    if (!form) return;
    var k = form.querySelector('.editkind').value;
    var personSel = form.querySelector('.editperson');
    if (ev.target.classList.contains('editkind')){
      var prev = personSel.value;
      personSel.innerHTML = personOptionsHtml(k, prev);
    }
    form.querySelector('.editmethod').hidden = k==='einzahlung' || personSel.value==='kasse';
  });

  // ---------- history ----------
  function fmtWhen(iso){
    return iso ? new Date(iso).toLocaleString('de-DE',{day:'2-digit',month:'2-digit',year:'2-digit',hour:'2-digit',minute:'2-digit'}) : '–';
  }
  function by(u){ return u ? ' <span class="tx-by">(' + esc(u) + ')</span>' : ''; }
  function describe(s){
    return (s.kind==='einzahlung'?'Einzahlung':'Ausgabe')+' · '+esc(s.person)+' · '+money(s.amount)+
      (s.kind==='ausgabe' && s.person_id!=null ? (s.method==='bar'?' · Bar (privat)':' · Karte') : '')+
      (s.note?' · „'+esc(s.note)+'“':'');
  }
  function renderHistory(){
    if (!state.tx.length){ $('historywrap').innerHTML = '<div class="empty">Noch keine Buchungen.</div>'; return; }
    var last = function(t){ return Math.max(ts(t.created_at), ts(t.updated_at), ts(t.deleted_at)); };
    var sorted = state.tx.slice().sort(function(a,b){ return last(b)-last(a); });
    $('historywrap').innerHTML = sorted.map(function(t){
      // Revisionen speichern den Stand *vor* der jeweiligen Bearbeitung.
      var states = t.revisions.concat([t]);
      var lines = ['<div class="hcline">Angelegt '+fmtWhen(t.created_at)+by(t.created_by)+': '+describe(states[0])+'</div>'];
      t.revisions.forEach(function(r, i){
        lines.push('<div class="hcline muted">Bearbeitet '+fmtWhen(r.changed_at)+by(r.changed_by)+' → '+describe(states[i+1])+'</div>');
      });
      if (t.deleted) lines.push('<div class="hcline neg">Gelöscht '+fmtWhen(t.deleted_at)+by(t.deleted_by)+'</div>');
      return '<div class="historycard'+(t.deleted?' deleted':'')+'">'+lines.join('')+'</div>';
    }).join('');
  }

  // ---------- shopping ----------
  function shopRow(s){
    if (s.id === expandedShopId) return shopRowExpanded(s);
    var meta = [s.qty, s.info].filter(Boolean).map(esc);
    return '<div class="shopitem '+(s.done?'done':'')+'" data-id="'+s.id+'">'+
      '<button class="chk '+(s.done?'done':'')+'" data-toggle-shop="'+s.id+'" title="Abhaken">'+(s.done?'✓':'')+'</button>'+
      '<div class="shopbody"><div class="txt">'+esc(s.text)+'</div>'+(meta.length?'<div class="shopmeta">'+meta.join(' · ')+'</div>':'')+'</div>'+
      '<div class="entryactions">'+
        '<button class="iconbtn" data-detail-shop="'+s.id+'" title="Menge &amp; Notiz">✎</button>'+
        '<button class="del" data-del-shop="'+s.id+'" title="Löschen">✕</button>'+
      '</div></div>';
  }
  function shopRowExpanded(s){
    return '<div class="shopitem '+(s.done?'done':'')+'" data-id="'+s.id+'">'+
      '<button class="chk '+(s.done?'done':'')+'" data-toggle-shop="'+s.id+'">'+(s.done?'✓':'')+'</button>'+
      '<div class="shopbody"><div class="txt">'+esc(s.text)+'</div>'+
        '<div class="shopdetail">'+
          '<input class="shopqty" placeholder="Menge, z. B. 2 Stück" maxlength="24" value="'+esc(s.qty)+'">'+
          '<input class="shopinfo" placeholder="Notiz, z. B. gekühlt lagern" maxlength="60" value="'+esc(s.info)+'">'+
          '<button class="btn primary small" data-save-shopdetail="'+s.id+'" style="flex:none">Speichern</button>'+
          '<button class="btn ghost small" data-cancel-shopdetail style="flex:none">Abbrechen</button>'+
        '</div></div>'+
      '<div class="entryactions"><button class="del" data-del-shop="'+s.id+'" title="Löschen">✕</button></div></div>';
  }

  function confirmDelete(btn, onConfirm){
    if (btn.dataset.confirming){ onConfirm(); return; }
    btn.dataset.confirming = '1';
    var old = btn.textContent;
    btn.textContent = '✓ sicher?';
    btn.style.color = 'var(--negative)';
    setTimeout(function(){ if (btn.dataset.confirming){ delete btn.dataset.confirming; btn.textContent = old; btn.style.color=''; } }, 3000);
  }
  function onEnter(inputId, btnId){
    $(inputId).addEventListener('keydown', function(e){ if (e.key==='Enter') $(btnId).click(); });
  }

  // ---------- writes: crew ----------
  $('addcrewbtn').addEventListener('click', function(){
    var input = $('newcrewname'), name = input.value.trim();
    if (!name) return;
    var btn = this; btn.disabled = true;
    api('crew/', {name:name}).then(function(){ input.value=''; }).catch(handleError)
      .then(function(){ btn.disabled = false; });
  });
  onEnter('newcrewname','addcrewbtn');

  $('crewgrid').addEventListener('click', function(ev){
    var edit = ev.target.closest('[data-edit-crew]');
    if (edit){
      editingCrewId = Number(edit.dataset.editCrew);
      var c = findById(state.crew, editingCrewId);
      var card = $('crewgrid').querySelector('[data-id="'+editingCrewId+'"]');
      if (c && card){ card.outerHTML = crewCardEditHtml(c); }
      var inp = $('crewgrid').querySelector('.crewrename');
      if (inp){ inp.focus(); inp.select(); }
      return;
    }
    if (ev.target.closest('[data-cancel-crew]')){ editingCrewId = null; render(); return; }
    var save = ev.target.closest('[data-save-crew]');
    if (!save) return;
    var input = save.closest('.crewcard').querySelector('.crewrename');
    var name = input.value.trim();
    if (!name){ input.focus(); return; }
    save.disabled = true;
    var id = save.dataset.saveCrew;
    editingCrewId = null;
    api('crew/'+id+'/', {name:name}).catch(function(e){
      editingCrewId = Number(id); save.disabled = false; input.style.borderColor = 'var(--negative)'; handleError(e);
    });
  });
  $('crewgrid').addEventListener('keydown', function(ev){
    if (ev.key==='Enter' && ev.target.classList.contains('crewrename')){
      ev.target.closest('.crewcard').querySelector('[data-save-crew]').click();
    }
  });

  // ---------- writes: transactions ----------
  $('addtxbtn').addEventListener('click', function(){
    var person = $('personsel').value;
    var amountEl = $('amount'), noteEl = $('note');
    var amount = parseFloat((amountEl.value||'').replace(',','.'));
    if (!person || !(amount>0)){ amountEl.focus(); return; }
    var btn = this; btn.disabled = true;
    api('tx/', {kind:kind, person_id:person, amount:amount, method:method, note:noteEl.value.trim()})
      .then(function(){ amountEl.value=''; noteEl.value=''; })
      .catch(handleError)
      .then(function(){ btn.disabled = false; });
  });

  $('ledgerwrap').addEventListener('click', function(ev){
    var edit = ev.target.closest('[data-edit-tx]');
    if (edit){
      editingTxId = Number(edit.dataset.editTx);
      var tx = findById(state.tx, editingTxId);
      var row = $('ledgerwrap').querySelector('[data-id="'+editingTxId+'"]');
      if (tx && row) row.outerHTML = txEditRowHtml(tx);
      return;
    }
    if (ev.target.closest('[data-cancel-edit]')){ editingTxId = null; render(); return; }
    var save = ev.target.closest('[data-save-edit]');
    if (save){
      var form = save.closest('.editform');
      var amount = parseFloat((form.querySelector('.editamount').value||'').replace(',','.'));
      if (!(amount>0)){ form.querySelector('.editamount').focus(); return; }
      var id = save.dataset.saveEdit;
      save.disabled = true;
      editingTxId = null;
      api('tx/'+id+'/', {
        kind: form.querySelector('.editkind').value,
        person_id: form.querySelector('.editperson').value,
        amount: amount,
        method: form.querySelector('.editmethod').value,
        note: form.querySelector('.editnote').value.trim()
      }).catch(function(e){ editingTxId = Number(id); save.disabled = false; handleError(e); });
      return;
    }
    var del = ev.target.closest('[data-del-tx]');
    if (del) confirmDelete(del, function(){ api('tx/'+del.dataset.delTx+'/delete/', {}).catch(handleError); });
  });

  // ---------- writes: shopping (für alle) ----------
  function addShop(text){ return api('shop/', {text:text}); }

  $('shopaddbtn').addEventListener('click', function(){
    var input = $('shopinput'), text = input.value.trim();
    if (!text) return;
    addShop(text).then(function(){ input.value=''; }).catch(handleError);
  });
  onEnter('shopinput','shopaddbtn');

  ['shopopen','shopdone'].forEach(function(listId){
    $(listId).addEventListener('click', function(ev){
      var tog = ev.target.closest('[data-toggle-shop]');
      if (tog){
        var item = findById(state.shop, tog.dataset.toggleShop);
        expandedShopId = null;
        api('shop/'+tog.dataset.toggleShop+'/', {done: !(item && item.done)}).catch(handleError);
        return;
      }
      var detail = ev.target.closest('[data-detail-shop]');
      if (detail){
        expandedShopId = Number(detail.dataset.detailShop);
        var s = findById(state.shop, expandedShopId);
        var row = detail.closest('.shopitem');
        if (s && row) row.outerHTML = shopRowExpanded(s);
        return;
      }
      if (ev.target.closest('[data-cancel-shopdetail]')){ expandedShopId = null; render(); return; }
      var save = ev.target.closest('[data-save-shopdetail]');
      if (save){
        var form = save.closest('.shopdetail');
        save.disabled = true;
        expandedShopId = null;
        api('shop/'+save.dataset.saveShopdetail+'/', {
          qty: form.querySelector('.shopqty').value.trim(),
          info: form.querySelector('.shopinfo').value.trim()
        }).catch(function(e){ save.disabled = false; handleError(e); });
        return;
      }
      var del = ev.target.closest('[data-del-shop]');
      if (del) confirmDelete(del, function(){ expandedShopId = null; api('shop/'+del.dataset.delShop+'/delete/', {}).catch(handleError); });
    });
  });

  // ---------- standard list: toggle, search, übernehmen ----------
  $('stdlistbtn').addEventListener('click', function(){
    var wrap = $('stdlistwrap');
    wrap.hidden = !wrap.hidden;
    this.textContent = wrap.hidden ? '📋 Standardliste für Segeltörns durchsuchen' : '📋 Standardliste ausblenden';
    if (!wrap.hidden) $('stdsearch').focus();
  });
  $('stdsearch').addEventListener('input', function(){
    var q = this.value.trim().toLowerCase();
    document.querySelectorAll('#stdlistwrap .stdcat').forEach(function(cat){
      var catHit = cat.querySelector('.stdcathead').textContent.toLowerCase().indexOf(q) >= 0;
      var any = false;
      cat.querySelectorAll('.stditem').forEach(function(it){
        var hit = !q || catHit || it.textContent.toLowerCase().indexOf(q) >= 0;
        it.classList.toggle('hidden', !hit);
        any = any || hit;
      });
      cat.classList.toggle('hidden', !any);
    });
  });
  $('stdlistwrap').addEventListener('click', function(ev){
    var b = ev.target.closest('[data-add-std]');
    if (!b) return;
    var old = b.textContent;
    b.disabled = true;
    addShop(b.dataset.addStd).then(function(){ b.textContent = '✓ Hinzugefügt'; }, function(e){
      if (e.status===409) b.textContent = 'Schon in der Liste'; else handleError(e);
    }).then(function(){ setTimeout(function(){ b.disabled = false; b.textContent = old; }, 1200); });
  });

  // ---------- live-ish updates ----------
  setInterval(function(){
    if (document.hidden || editingTxId || editingCrewId || expandedShopId) return;
    var active = document.activeElement;
    if (active && (active.tagName==='INPUT' || active.tagName==='SELECT') && active.value) return;
    api('state/').catch(function(e){ console.warn('refresh failed', e); });
  }, POLL_MS);

  render();
})();

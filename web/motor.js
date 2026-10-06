/* heat2cool · motor de cálculo en JavaScript.
 * Traducción línea a línea de heat2cool/motor.py y heat2cool/estudio.py: si cambias uno, cambia el otro.
 * tests/test_paridad.py comprueba con Node que ambos dan los mismos números.
 */
const H2C = (function () {
  const K = 273.15, INF = Infinity, KW_POR_M3H_K = 1.1611, G = 9.81;

  const dist = (x, lo, hi) => (x < lo ? lo - x : x > hi ? x - hi : 0);
  const nivel = (origen, d) => (origen === "generico" ? 0 : d <= 2 ? 1 : d <= 10 ? 2 : 3);
  const media = (xs) => xs.reduce((a, b) => a + b, 0) / xs.length;
  function recta(xs, ys) {
    const mx = media(xs), my = media(ys);
    let sxx = 0, sxy = 0;
    for (let i = 0; i < xs.length; i++) { sxx += (xs[i] - mx) ** 2; sxy += (xs[i] - mx) * (ys[i] - my); }
    if (sxx < 1) return [my, 0];
    const b = sxy / sxx;
    return [my - b * mx, b];
  }

  // ------------------------------------------------------------- bomba de calor
  const bdcSalto = (c, ts, tk) => Math.max((tk + c["bdc.ap_cond"]) - (ts - c["bdc.ap_evap"]), 5);
  const bdcCarnot = (c, ts, tk) => (tk + c["bdc.ap_cond"] + K) / bdcSalto(c, ts, tk);

  function ajustarBdc(c, eq) {
    const pts = eq.puntos;
    const saltos = pts.map((p) => bdcSalto(c, p.ts, p.tk));
    const etas = pts.map((p) => p.cop / bdcCarnot(c, p.ts, p.tk));
    const [a, b] = recta(saltos, etas);
    const pq = [];
    pts.forEach((p, i) => { if (p.q) pq.push([saltos[i], p.q]); });
    let sRef, qRef, k;
    if (pq.length) {
      const [qa, qb] = recta(pq.map((x) => x[0]), pq.map((x) => x[1]));
      sRef = media(pq.map((x) => x[0]));
      qRef = qa + qb * sRef;
      k = qb !== 0 ? qb / qRef : c["bdc.k_cap"];
      k = Math.min(Math.max(k, -0.03), 0.01);
    } else { sRef = media(saltos); qRef = INF; k = 0; }
    return { tipo: "bdc", origen: eq.origen, a, b, s_min: Math.min(...saltos), s_max: Math.max(...saltos),
      ts_min: Math.min(...pts.map((p) => p.ts)), ts_max: Math.max(...pts.map((p) => p.ts)),
      tk_min: Math.min(...pts.map((p) => p.tk)), tk_max: Math.max(...pts.map((p) => p.tk)),
      q_ref: qRef, s_ref: sRef, k, n_puntos: pts.length };
  }

  function bdcEn(c, m, ts, tk) {
    const s = bdcSalto(c, ts, tk);
    const sCl = Math.min(Math.max(s, m.s_min), m.s_max);
    const eta = m.a + m.b * sCl;
    const cop = Math.max(eta * bdcCarnot(c, ts, tk), 1.05);
    const cap = m.q_ref === INF ? INF : m.q_ref * Math.max(1 + m.k * (s - m.s_ref), 0.1);
    const d = Math.max(dist(ts, m.ts_min, m.ts_max), dist(tk, m.tk_min, m.tk_max));
    return { cop, cap, q_nom: m.q_ref, nivel: nivel(m.origen, d), dist: d };
  }

  // ------------------------------------------------------------- absorción
  function absIdeal(c, tg, tc, tr) {
    const Tg = tg - c["abs.ap_gen"] + K, Te = tc - c["abs.ap_evap"] + K, Ta = tr + c["abs.ap_abs"] + K;
    if (Tg <= Ta + 1 || Ta <= Te) return 0;
    return (1 - Ta / Tg) * Te / (Ta - Te);
  }

  function ajustarAbs(c, eq) {
    const pts = eq.puntos;
    const etas = pts.map((p) => p.cop / absIdeal(c, p.tg, p.tc, p.tr));
    const pq = pts.filter((p) => p.q);
    const m = { tipo: "absorcion", origen: eq.origen, eta: media(etas), n_puntos: pts.length,
      tg_ref: media(pts.map((p) => p.tg)), tc_ref: media(pts.map((p) => p.tc)), tr_ref: media(pts.map((p) => p.tr)),
      q_ref: pq.length ? media(pq.map((p) => p.q)) : INF };
    for (const v of ["tg", "tc", "tr"]) {
      m[v + "_min"] = Math.min(...pts.map((p) => p[v]));
      m[v + "_max"] = Math.max(...pts.map((p) => p[v]));
    }
    return m;
  }

  const absFactorCap = (c, m, tg, tc, tr) => Math.max(1 + c["abs.k_gen"] * (tg - m.tg_ref)
    + c["abs.k_frio"] * (tc - m.tc_ref) - c["abs.k_refrig"] * (tr - m.tr_ref), 0);

  function absEn(c, m, tg, tc, tr) {
    const ideal = absIdeal(c, tg, tc, tr);
    const cop = Math.min(m.eta * ideal, 0.80);
    const f = ideal > 0 ? absFactorCap(c, m, tg, tc, tr) : 0;
    const cap = m.q_ref === INF ? INF : m.q_ref * f;
    const d = Math.max(dist(tg, m.tg_min, m.tg_max), dist(tc, m.tc_min, m.tc_max), dist(tr, m.tr_min, m.tr_max));
    return { cop, cap, q_nom: m.q_ref, f_cap: f, nivel: nivel(m.origen, d), dist: d };
  }

  // ------------------------------------------------------------- enfriadora y agua
  function enfCarnot(c, t) { const te = t - 3 + K; return te / (c["enf.t_cond"] + K - te); }
  const enfEer = (c, t) => c["enf.eer_ref"] * enfCarnot(c, t) / enfCarnot(c, c["enf.t_ref"]);
  const aguaTorre = (c) => 3600 / 2430 * c["rech.ciclos"] / (c["rech.ciclos"] - 1);
  const caudal = (q, dt) => (dt > 0 ? q / (KW_POR_M3H_K * dt) : 0);
  const pBomba = (c, m3h, h) => m3h / 3600 * 1000 * G * h / c["bomb.rend"] / 1000;

  // ------------------------------------------------------------- sistema
  function modelos(c, cat) {
    const get = (ruta, tipo) => {
      const eq = cat[c[ruta]];
      if (!eq) throw new Error(`Equipo '${c[ruta]}' (${ruta}) no está en el catálogo`);
      if (eq.tipo !== tipo) throw new Error(`'${c[ruta]}' es de tipo ${eq.tipo}, se esperaba ${tipo}`);
      return tipo === "bdc" ? ajustarBdc(c, eq) : ajustarAbs(c, eq);
    };
    return { bdc1: get("eq.bdc1", "bdc"), abs: get("eq.abs", "absorcion"), r2: get("eq.r2", "bdc") };
  }

  function nAuto(fijo, req, cap) {
    if (fijo && fijo > 0) return Math.trunc(fijo);
    if (cap === INF || req <= 0) return 1;
    return Math.max(1, Math.ceil(req / cap - 1e-6));
  }

  function dimensionar(c, ms) {
    const hp = bdcEn(c, ms.bdc1, c["cpd.t_ret"], c["cal.t_ida"]);
    const ab = absEn(c, ms.abs, c["cal.t_ida"], c["frio.t_imp"], c["rech.t_ent"]);
    const r2 = bdcEn(c, ms.r2, c["rech.t_ent"], c["rec.r2_t_sal"]);
    const qGen0 = c["cpd.q_kw"] * hp.cop / (hp.cop - 1);
    const qFrioReq = Math.min(c["frio.demanda_kw"], ab.cop * qGen0);
    const qGenReq = ab.cop > 0 ? qFrioReq / ab.cop : 0;
    return { hp, ab, r2, n_hp: nAuto(c["n.bdc1"], qGenReq, hp.cap), n_ab: nAuto(c["n.abs"], qFrioReq, ab.cap),
      n_r2: nAuto(c["n.r2"], c["rec.r2_kw"], r2.cap), q_gen_req: qGenReq, q_frio_req: qFrioReq };
  }

  const plr = (q, n, cap) => (cap === INF ? 1 : cap > 0 ? q / (n * cap) : 0);

  function punto(c, d, carga, recOn) {
    const { hp, ab, r2 } = d;
    const dem = c["frio.demanda_kw"];
    const qSrc = c["cpd.q_kw"] * carga;
    let copHp = hp.cop, copAb = ab.cop;
    const capHp = d.n_hp * hp.cap, capAb = d.n_ab * ab.cap;
    let qGen = 0, qFrio = 0, limitante = "Absorción sin ciclo (T generador demasiado baja)", plrHp = 0, plrAb = 0;
    for (let it = 0; it < 4; it++) {
      const qGen0 = qSrc * copHp / (copHp - 1);
      const qFrio0 = copAb * qGen0;
      if (qFrio0 <= 0) { qGen = 0; qFrio = 0; break; }
      const lims = [["Calor disponible del CPD", 1], ["Demanda de frío", dem / qFrio0],
        ["Capacidad de la absorción", capAb / qFrio0], ["Capacidad de la BdC 1", capHp / qGen0]];
      let s;
      [limitante, s] = lims[0];
      for (const [nombre, v] of lims.slice(1)) if (v < s - 1e-12) { limitante = nombre; s = v; }
      qGen = qGen0 * s; qFrio = qFrio0 * s;
      plrHp = plr(qGen, d.n_hp, hp.cap); plrAb = plr(qFrio, d.n_ab, ab.cap);
      copHp = Math.max(hp.cop * (1 - c["bdc.pen_carga"] * (1 - plrHp)), 1.05);
      copAb = ab.cop * (1 - c["abs.pen_carga"] * (1 - plrAb));
    }
    const wHp = qGen / copHp, qEvap = qGen - wHp, qRej = qGen + qFrio;
    let qR1 = 0, qR2 = 0, qR2Ext = 0, wR2 = 0;
    if (recOn) {
      qR1 = Math.min(c["rec.r1_kw"], qRej);
      qR2 = Math.min(c["rec.r2_kw"], (qRej - qR1) * r2.cop / (r2.cop - 1), d.n_r2 * r2.cap);
      wR2 = qR2 / r2.cop; qR2Ext = qR2 - wR2;
    }
    const qDis = qRej - qR1 - qR2Ext;
    const qTorre = Math.min(qDis, c["rech.torre_kw"]), qAdiab = Math.max(0, qDis - c["rech.torre_kw"]);
    const fCpd = caudal(qEvap, c["cpd.t_sal"] - c["cpd.t_ret"]), fCal = caudal(qGen, c["cal.t_ida"] - c["cal.t_ret"]);
    const fFrio = caudal(qFrio, c["frio.t_ret"] - c["frio.t_imp"]), fRech = caudal(qRej, c["rech.t_sal"] - c["rech.t_ent"]);
    const pBombas = pBomba(c, fCpd, c["bomb.h_cpd"]) + pBomba(c, fCal, c["bomb.h_cal"]) + pBomba(c, fRech, c["bomb.h_rech"]);
    const pAux = c["abs.aux_kwe_kw"] * qFrio;
    const pVent = c["rech.torre_kwe_kw"] * qTorre + c["rech.adiab_kwe_kw"] * qAdiab;
    const pDc = c["cpd.dry_cooler_kwe_kw"] * qEvap;
    const pSis = wHp + wR2 + pAux + pVent + pBombas - pDc;
    const eer = enfEer(c, c["frio.t_imp"]);
    const qRes = Math.max(dem - qFrio, 0), pEnf = qRes / eer;
    const aguaLh = aguaTorre(c) * (qTorre + qRes + pEnf) + c["rech.adiab_l_kwh"] * qAdiab;
    return { carga, rec: recOn, limitante, cop_bdc1: copHp, cop_abs: copAb, cop_r2: r2.cop, eer_enf: eer,
      plr_bdc1: plrHp, plr_abs: plrAb, q_cpd_disp: qSrc, q_evap: qEvap, w_bdc1: wHp, q_gen: qGen, q_frio: qFrio,
      q_rej: qRej, q_r1: qR1, q_r2: qR2, q_r2_ext: qR2Ext, w_r2: wR2, q_dis: qDis, q_torre: qTorre, q_adiab: qAdiab,
      q_enf: qRes, p_enf: pEnf, p_bombas: pBombas, p_aux_abs: pAux, p_vent: pVent, p_dc_ahorro: pDc, p_sis: pSis,
      agua_l_h: aguaLh, f_cpd: fCpd, f_cal: fCal, f_frio: fFrio, f_rech: fRech };
  }

  const crf = (i, n) => i * (1 + i) ** n / ((1 + i) ** n - 1);

  function capex(c, d, recOn, pDis) {
    const { hp, ab, r2 } = d;
    const nomHp = hp.q_nom === INF ? d.q_gen_req : d.n_hp * hp.q_nom;
    let nomAb;
    if (ab.q_nom === INF) { const f = ab.f_cap > 0 ? ab.f_cap : 1; nomAb = d.q_frio_req / Math.max(f, 0.3); }
    else nomAb = d.n_ab * ab.q_nom;
    const nomR2 = r2.q_nom === INF ? c["rec.r2_kw"] : d.n_r2 * r2.q_nom;
    const cHp = c["eco.capex_bdc"] * nomHp, cAb = c["eco.capex_abs"] * nomAb, cAd = c["eco.capex_adiab"] * pDis.q_adiab;
    const cR1 = recOn ? c["eco.capex_r1"] * c["rec.r1_kw"] : 0, cR2 = recOn ? c["eco.capex_r2"] * nomR2 : 0;
    const eq = cHp + cAb + cAd + cR1 + cR2;
    return { capex_bdc1: cHp, capex_abs: cAb, capex_adiab: cAd, capex_r1: cR1, capex_r2: cR2,
      capex_bop: eq * c["eco.bop"], capex_total: eq * (1 + c["eco.bop"]), nom_bdc1_kw: nomHp, nom_abs_kw: nomAb,
      nom_r2_kw: recOn ? nomR2 : 0, nom_adiab_kw: pDis.q_adiab };
  }

  function evaluar(c, cat, modo) {
    const recModo = modo === "con_recuperacion";
    const ms = modelos(c, cat), d = dimensionar(c, ms), pDis = punto(c, d, 1, false);
    const cov = recModo ? c["rec.cobertura"] : 0;
    const subs = recModo ? [[1 - cov, false], [cov, true]] : [[1, false]];
    const h = c["cpd.horas"];
    const acc = { e_sis: 0, e_enf: 0, agua: 0, frio: 0, calor: 0, rej: 0, adiab: 0, w_bdc1: 0, w_r2: 0,
      bombas: 0, vent: 0, aux: 0, dc: 0 };
    const cargas = [];
    for (const [carga, peso] of c.perfil) {
      for (const [wSub, on] of subs) {
        if (wSub <= 0) continue;
        const w = peso * wSub, p = punto(c, d, carga, on);
        p.peso = w; cargas.push(p);
        acc.e_sis += w * p.p_sis * h; acc.e_enf += w * p.p_enf * h; acc.agua += w * p.agua_l_h * h / 1000;
        acc.frio += w * p.q_frio * h; acc.calor += w * (p.q_r1 + p.q_r2) * h; acc.rej += w * p.q_rej * h;
        acc.adiab += w * p.q_adiab * h; acc.w_bdc1 += w * p.w_bdc1 * h; acc.w_r2 += w * p.w_r2 * h;
        acc.bombas += w * p.p_bombas * h; acc.vent += w * p.p_vent * h; acc.aux += w * p.p_aux_abs * h;
        acc.dc += w * p.p_dc_ahorro * h;
      }
    }
    const cx = capex(c, d, recModo, pDis);
    const cElec = (acc.e_sis + acc.e_enf) * c["eco.elec"], cAgua = acc.agua * c["eco.agua"];
    const cMant = c["eco.mant"] * cx.capex_total;
    const credito = acc.calor * c["rec.precio_calor"] / c["rec.rend_caldera"];
    const capexAnual = crf(c["eco.tasa"], c["eco.vida"]) * cx.capex_total;
    const J = cElec + cAgua + cMant + capexAnual - credito;
    const dem = c["frio.demanda_kw"], eer = enfEer(c, c["frio.t_imp"]);
    const eBase = dem / eer * h, aguaBase = aguaTorre(c) * (dem + dem / eer) * h / 1000;
    const cElecBase = eBase * c["eco.elec"], cAguaBase = aguaBase * c["eco.agua"], JBase = cElecBase + cAguaBase;
    const ahorroOp = JBase - (cElec + cAgua + cMant - credito);
    const eTot = acc.e_sis + acc.e_enf;
    return Object.assign({ modo, cop_bdc1: d.hp.cop, cop_abs: d.ab.cop, cop_r2: d.r2.cop, eer_enf: eer,
      cal_bdc1: d.hp.nivel, cal_abs: d.ab.nivel, cal_r2: recModo ? d.r2.nivel : 0,
      n_bdc1: d.n_hp, n_abs: d.n_ab, n_r2: recModo ? d.n_r2 : 0,
      cap_bdc1_kw: d.hp.cap, cap_abs_kw: d.ab.cap, cap_r2_kw: d.r2.cap,
      limitante: pDis.limitante, frio_dis_kw: pDis.q_frio, cobertura_frio: pDis.q_frio / dem,
      frio_mwh: acc.frio / 1e3, calor_rec_mwh: acc.calor / 1e3, rechazo_mwh: acc.rej / 1e3,
      elec_sis_mwh: acc.e_sis / 1e3, elec_enf_mwh: acc.e_enf / 1e3, elec_base_mwh: eBase / 1e3,
      ahorro_elec_mwh: (eBase - eTot) / 1e3, e_bdc1_mwh: acc.w_bdc1 / 1e3, e_r2_mwh: acc.w_r2 / 1e3,
      e_bombas_mwh: acc.bombas / 1e3, e_vent_mwh: acc.vent / 1e3, e_aux_mwh: acc.aux / 1e3,
      e_dc_ahorro_mwh: acc.dc / 1e3, agua_m3: acc.agua, agua_base_m3: aguaBase,
      eer_sis: acc.e_sis > 0 ? acc.frio / acc.e_sis : 0,
      c_elec: cElec, c_agua: cAgua, c_mant: cMant, capex_anual: capexAnual, credito_calor: credito,
      c_elec_base: cElecBase, c_agua_base: cAguaBase, J, J_base: JBase, ahorro_neto: JBase - J,
      ahorro_operacion: ahorroOp, retorno_anos: ahorroOp > 0 ? cx.capex_total / ahorroOp : INF }, cx,
    { diseno: pDis, cargas });
  }

  const con = (c, ruta, v) => Object.assign({}, c, { [ruta]: v });

  // ------------------------------------------------------------- estudio
  function biseccion(f, lo, hi, it = 60) {
    let flo = f(lo); const fhi = f(hi);
    if (flo === 0) return lo;
    if (flo * fhi > 0) return null;
    for (let i = 0; i < it; i++) {
      const mid = 0.5 * (lo + hi), fm = f(mid);
      if ((fm < 0) === (flo < 0)) { lo = mid; flo = fm; } else hi = mid;
    }
    return 0.5 * (lo + hi);
  }

  function equilibrios(c, cat, modo) {
    const ah = (ruta) => (x) => evaluar(con(c, ruta, x), cat, modo).ahorro_neto;
    return { eer_equilibrio: biseccion(ah("enf.eer_ref"), 0.5, 15), elec_equilibrio: biseccion(ah("eco.elec"), 0, 2) };
  }

  function sensibilidad(c, cat, modo, rutas, delta = 0.2) {
    const ref = evaluar(c, cat, modo).ahorro_neto;
    return rutas.map((r) => {
      const v0 = c[r];
      const lo = evaluar(con(c, r, v0 * (1 - delta)), cat, modo).ahorro_neto;
      const hi = evaluar(con(c, r, v0 * (1 + delta)), cat, modo).ahorro_neto;
      return { ruta: r, valor: v0, ahorro_menos: lo, ahorro_mas: hi, ahorro_ref: ref, rango: Math.abs(hi - lo) };
    }).sort((a, b) => b.rango - a.rango);
  }

  return { evaluar, equilibrios, sensibilidad, biseccion, con, modelos, dimensionar, punto, INF };
})();
if (typeof module !== "undefined") module.exports = H2C;

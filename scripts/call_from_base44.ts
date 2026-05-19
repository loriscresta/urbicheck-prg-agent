/**
 * Snippet Deno/TypeScript da aggiungere in wfsLiguria/entry.ts
 * per chiamare il microservizio PRG Agent esterno.
 *
 * Sostituisce il WMS GetFeatureInfo con dati shapefile molto più ricchi.
 */

const PRG_AGENT_URL = Deno.env.get("PRG_AGENT_URL") ?? "https://prg-agent.railway.app";
// Imposta PRG_AGENT_URL nelle env vars di Base44 dopo il deploy su Railway

interface PRGResult {
  comune: string;
  zona_urbanistica: {
    destinazione: string;
    compromissione: string;
    caratteristica: string;
    sigla_piano: string;
    area_mq: number;
    distanza_bordo_m?: number;
  } | null;
  vincoli: Array<{
    codice: string;
    descrizione: string;
    gravita: "alto" | "medio" | "basso" | "info";
    area_mq?: number;
  }>;
  mod_intervento: Array<{
    codice: string;
    tipo: string;
    descrizione: string;
  }>;
  caratt_storica: Array<{
    destinazione: string;
    caratteristica: string;
  }>;
  fonte: string;
  note: string | null;
}

/**
 * Chiama il PRG Agent e restituisce i dati di piano regolatore.
 * Da usare in wfsLiguria al posto del WMS GetFeatureInfo per la zona urbanistica.
 */
export async function queryPRGAgent(
  comune: string,
  lat: number,
  lon: number
): Promise<PRGResult | null> {
  try {
    const resp = await fetch(`${PRG_AGENT_URL}/query`, {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ comune: comune.toLowerCase(), lat, lon }),
      signal: AbortSignal.timeout(10_000), // 10s timeout
    });

    if (!resp.ok) {
      const err = await resp.text();
      console.error(`PRG Agent error ${resp.status}: ${err}`);
      return null;
    }

    return await resp.json() as PRGResult;
  } catch (e) {
    console.error(`PRG Agent non raggiungibile: ${e}`);
    return null;
  }
}

/**
 * Converte i risultati PRG nel formato atteso da report_data.wfs_liguria
 * e li integra con i dati già presenti.
 */
export function integratePRGData(
  prg: PRGResult,
  existing: Record<string, unknown>
): Record<string, unknown> {
  const zona = prg.zona_urbanistica;

  // Zona urbanistica
  const zonaUrbanistica = zona ? {
    disponibile: true,
    destinazione: zona.destinazione,
    compromissione: zona.compromissione,
    caratteristica: zona.caratteristica,
    sigla_piano: zona.sigla_piano || null,
    area_zona_mq: zona.area_mq,
    messaggio: `${zona.destinazione} — ${zona.compromissione}${zona.caratteristica ? " — " + zona.caratteristica : ""}`,
    fonte: prg.fonte,
    fonte_ok: true,
  } : {
    disponibile: false,
    messaggio: prg.note ?? "Zona urbanistica non trovata nel PRG.",
    fonte: prg.fonte,
    fonte_ok: true,
  };

  // Vincoli PRG (aggiuntivi rispetto ai vincoli ope legis)
  const vincoliPRG = prg.vincoli.map((v) => ({
    codice: v.codice,
    descrizione: v.descrizione,
    gravita: v.gravita,
    fonte: "PRG comunale — Mosaicatura Piemonte",
  }));

  // Modalità di intervento
  const modIntervento = prg.mod_intervento.map((m) => ({
    codice: m.codice,
    tipo: m.tipo,
    descrizione: m.descrizione,
  }));

  return {
    ...existing,
    zona_urbanistica: zonaUrbanistica,
    vincoli_prg: vincoliPRG,
    mod_intervento: modIntervento,
    caratt_storica: prg.caratt_storica,
    prg_fonte: prg.fonte,
  };
}

// ============================================================
// Esempio di utilizzo in wfsLiguria/entry.ts:
// ============================================================
//
// // Dopo aver ottenuto lat/lon del centroide:
// const regione = q.regione ?? "piemonte";
// if (regione === "piemonte") {
//   const comune = q.comune ?? "";
//   const prg = await queryPRGAgent(comune, lat, lon);
//   if (prg) {
//     risultati = integratePRGData(prg, risultati);
//     console.log(`PRG Agent: zona=${prg.zona_urbanistica?.destinazione}, vincoli=${prg.vincoli.length}`);
//   }
// }

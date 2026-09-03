# Mensaje WhatsApp — Estructura real (n8n)

## Código n8n (Code node) que genera el texto

```javascript
return items.map(item => {
  const nombre         = item.json.nombre;
  const titulo         = item.json.titulo;
  const departamento   = item.json.departamento;
  const provincia      = item.json.provincia;
  const distrito       = item.json.distrito;
  const cultivo        = item.json.cultivo;
  const nivel          = item.json.nivel;
  const duracion_horas = item.json.duracion_horas;
  const mensaje_texto  = item.json.mensaje_texto; // guardado en clientes_envios

  const fechaInicio = new Date(item.json.fecha_inicio).toLocaleDateString('es-PE');
  const fechaFin    = new Date(item.json.fecha_fin).toLocaleDateString('es-PE');

  const nivelMap = {
    "Rojo":     "🔴 NIVEL ROJO\n(Es muy probable que ocurra, tome precauciones hoy)",
    "Naranja":  "🟠 NIVEL NARANJA\n(Se espera que ocurra, es recomendable prepararse)",
    "Amarillo": "🟡 NIVEL AMARILLO\n(Podría presentarse, esté atento)"
  };

  const nivelTexto = nivelMap[nivel] || `NIVEL ${nivel}`;

  const mensaje =
`${titulo}
${departamento}, ${provincia}, ${distrito}

Estimado/a agricultor/a ${nombre}, La Positiva informa posible ${titulo} en su distrito que puede afectar su cultivo de ${cultivo} desde ${fechaInicio} hasta ${fechaFin}, duración de ${duracion_horas} horas.

${nivelTexto}

⚠️ RECOMENDACIONES:
${mensaje_texto}

_La Positiva, cerca de ti 🧡_`;

  return { json: { ...item.json, mensaje } };
});
```

---

## Ejemplo real — Aviso 19 (LLUVIA EN LA SELVA)

> Llega al cliente junto con la imagen: `OUTPUT/aviso_19/SAN MARTIN.webp`

```
LLUVIA EN LA SELVA
San Martín, Tocache, Pólvora

Estimado/a agricultor/a VICTOR, La Positiva informa posible LLUVIA EN LA SELVA
en su distrito que puede afectar su cultivo de CÍTRICOS desde 22/01/2026 hasta
23/01/2026, duración de 47 horas.

🟠 NIVEL NARANJA
(Se espera que ocurra, es recomendable prepararse)

⚠️ RECOMENDACIONES:
- Se espera que vengan lluvias fuertes con vientos que pueden sacudir sus plantas,
  revise que sus canales de drenaje estén limpios para que el agua no se empoce.
- Para sus naranjos y limoneros, la mucha agua puede pudrir las raíces, asegúrese
  de que la tierra no quede encharcada alrededor del tronco.
- Como la lluvia va a durar casi dos días seguidos, esté atento a los frutos casi
  maduros, el viento podría botarlos antes de tiempo.

_La Positiva, cerca de ti 🧡_
```

---

## Campos que n8n necesita (vista `v_clientes_por_aviso_completo`)

| Variable n8n    | Campo BD                               |
|-----------------|----------------------------------------|
| `nombre`        | `clientes.nombre`                      |
| `titulo`        | `avisos.titulo`                        |
| `departamento`  | `v_clientes.departamento`              |
| `provincia`     | `v_clientes.provincia`                 |
| `distrito`      | `v_clientes.distrito`                  |
| `cultivo`       | `v_clientes.cultivo`                   |
| `nivel`         | `clientes_por_aviso.nivel`             |
| `duracion_horas`| `avisos.duracion_horas`                |
| `fecha_inicio`  | `avisos.fecha_inicio`                  |
| `fecha_fin`     | `avisos.fecha_fin`                     |
| `mensaje_texto` | `clientes_envios.mensaje_texto`        |
| imagen          | `OUTPUT/aviso_{n}/{departamento}.webp` |

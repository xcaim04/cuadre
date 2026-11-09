---
title: Ruta Cobrada · el efectivo en la calle
---

```sql cierre
SELECT fecha, en_mensajeros::DOUBLE AS en_mensajeros, en_oficina::DOUBLE AS en_oficina,
       depositado_acum::DOUBLE AS depositado_acum
FROM ruta_cobrada.cierre_caja
ORDER BY fecha
```

```sql deuda_hoy
SELECT coalesce(m.nombre, d.id_mensajero) AS mensajero, d.id_mensajero, d.deuda::DOUBLE AS deuda,
       d.deuda_0_2::DOUBLE AS deuda_0_2, d.deuda_3_7::DOUBLE AS deuda_3_7, d.deuda_mas_7::DOUBLE AS deuda_mas_7,
       d.deuda / sum(d.deuda) OVER () AS parte
FROM ruta_cobrada.deuda_mensajero_dia d
LEFT JOIN ruta_cobrada.mensajeros m USING (id_mensajero)
WHERE d.fecha = (SELECT max(fecha) FROM ruta_cobrada.deuda_mensajero_dia)
ORDER BY d.deuda DESC
```

```sql totales
SELECT strftime(max(fecha), '%d/%m/%Y') AS fecha, sum(deuda) AS deuda, sum(deuda_3_7 + deuda_mas_7) AS deuda_vieja,
       (SELECT count(*) FROM ruta_cobrada.pedidos_perdidos) AS perdidos,
       (SELECT sum(importe_actual)::DOUBLE FROM ruta_cobrada.pedidos_perdidos) AS importe_perdido
FROM ${deuda_hoy}, (SELECT max(fecha) AS fecha FROM ruta_cobrada.deuda_mensajero_dia)
```

Al cierre del <Value data={totales} column=fecha />, los mensajeros tenían <Value data={totales} column=deuda fmt="#,##0.00" /> en efectivo cobrado y sin liquidar. <Value data={deuda_hoy} column=mensajero row=0 /> tenía <Value data={deuda_hoy} column=parte row=0 fmt=pct0 /> de esa deuda: desde finales de septiembre pasa menos por la oficina y liquida solo una parte de lo que cobra.

<Grid cols=4>
  <BigValue data={totales} value=deuda title="Deuda de los mensajeros" fmt="#,##0" />
  <BigValue data={deuda_hoy} value=deuda title="De ella, {deuda_hoy[0].mensajero}" fmt="#,##0" />
  <BigValue data={totales} value=deuda_vieja title="Con más de 2 días" fmt="#,##0" />
  <BigValue data={totales} value=perdidos title="Pedidos perdidos" />
</Grid>

## Quién tiene el efectivo

La deuda de cada mensajero, por antigüedad. Lo que liquida paga primero sus cobros más viejos.

```sql por_tramo
SELECT mensajero, '0–2 días' AS tramo, 1 AS orden, deuda_0_2 AS deuda FROM ${deuda_hoy}
UNION ALL SELECT mensajero, '3–7 días', 2, deuda_3_7 FROM ${deuda_hoy}
UNION ALL SELECT mensajero, 'Más de 7 días', 3, deuda_mas_7 FROM ${deuda_hoy}
ORDER BY orden
```

<!-- Una rampa de un solo tono: más oscuro = más viejo. -->
<BarChart data={por_tramo} x=mensajero y=deuda series=tramo swapXY=true type=stacked yFmt="#,##0"
          sort=false title="Deuda por mensajero al cierre" colorPalette={['#86b6ef', '#2a78d6', '#104281']} />

```sql deuda_diaria
SELECT d.fecha, CASE WHEN d.id_mensajero = 'M05' THEN coalesce(m.nombre, 'M05') ELSE 'Los otros siete' END AS grupo,
       sum(d.deuda)::DOUBLE AS deuda
FROM ruta_cobrada.deuda_mensajero_dia d
LEFT JOIN ruta_cobrada.mensajeros m USING (id_mensajero)
GROUP BY ALL ORDER BY fecha, grupo
```

<!-- Las series van en orden alfabético: «Los otros siete» en gris, el mensajero atrasado en naranja. -->
<LineChart data={deuda_diaria} x=fecha y=deuda series=grupo yFmt="#,##0" xFmt="d mmm"
           title="Deuda acumulada al cierre de cada día" colorPalette={['#8e8e93', '#eb6834']} />

## Dónde está el efectivo cada día

El cierre de caja reparte lo cobrado entre lo que siguen teniendo los mensajeros y lo que ya está en la oficina sin depositar.

<AreaChart data={cierre} x=fecha y={['en_mensajeros', 'en_oficina']} yFmt="#,##0" xFmt="d mmm"
           title="Efectivo fuera del banco al cierre" colorPalette={['#2a78d6', '#1baf7a']} />

## ¿Cuadra?

El número piloto, recalculado desde gold: lo cobrado menos lo devuelto y lo liquidado tiene que dar la deuda de los ocho mensajeros, y lo liquidado menos lo depositado, el efectivo en la oficina.

```sql cuadre
WITH t AS (
  SELECT sum(cobrado) AS cobrado, sum(devuelto) AS devuelto, sum(liquidado) AS liquidado, sum(depositado) AS depositado
  FROM ruta_cobrada.cierre_caja
), ultimo AS (
  SELECT * FROM ruta_cobrada.cierre_caja ORDER BY fecha DESC LIMIT 1
)
SELECT 'Deuda de los mensajeros' AS cuenta, (t.cobrado - t.devuelto - t.liquidado)::DOUBLE AS desde_movimientos,
       (SELECT sum(deuda) FROM ${deuda_hoy}) AS desde_saldos, ultimo.en_mensajeros::DOUBLE AS en_cierre
FROM t, ultimo
UNION ALL
SELECT 'Efectivo en la oficina', (t.liquidado - t.depositado)::DOUBLE, NULL, ultimo.en_oficina::DOUBLE
FROM t, ultimo
```

<DataTable data={cuadre}>
  <Column id=cuenta title="Cuenta" />
  <Column id=desde_movimientos title="Suma de movimientos" fmt="#,##0.00" />
  <Column id=desde_saldos title="Suma por mensajero" fmt="#,##0.00" />
  <Column id=en_cierre title="Cierre de caja" fmt="#,##0.00" />
</DataTable>

## Pedidos perdidos

Pedidos sin entrega ni rechazo válidos más de 3 días después de creados. Los que tienen motivo están en cuarentena: la app los marcó entregados, pero sin cobro.

```sql perdidos
SELECT p.id_pedido, coalesce(m.nombre, p.id_mensajero) AS mensajero, p.cliente, p.importe_actual::DOUBLE AS importe,
       p.creado_en, p.dias_sin_cierre, p.motivo_cuarentena
FROM ruta_cobrada.pedidos_perdidos p
LEFT JOIN ruta_cobrada.mensajeros m USING (id_mensajero)
ORDER BY p.dias_sin_cierre DESC, p.id_pedido
```

<DataTable data={perdidos} rows=10 search=true>
  <Column id=id_pedido title="Pedido" />
  <Column id=mensajero title="Mensajero" />
  <Column id=cliente title="Cliente" />
  <Column id=importe title="Importe" fmt="#,##0.00" />
  <Column id=creado_en title="Creado" fmt="d mmm" />
  <Column id=dias_sin_cierre title="Días sin cierre" />
  <Column id=motivo_cuarentena title="Cuarentena" />
</DataTable>

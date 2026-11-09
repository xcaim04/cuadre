-- Los tramos de antigüedad suman la deuda (o cero si la oficina le debe al mensajero).
SELECT fecha, id_mensajero FROM gold.deuda_mensajero_dia
WHERE deuda_0_2 + deuda_3_7 + deuda_mas_7 <> greatest(deuda, 0);

GUÍA ESP-32



## Reglas

- Haz todas las conexiones con el USB desconectado. El USB se conecta solo en el paso 7.
- No uses el pin VIN: entrega 5 V y daña los micrófonos.
- Nunca unas el riel + con el riel − con un cable.
- Ubica cada pin por el nombre impreso en la placa. Las filas y columnas de esta guía suponen el ESP32 de 30 pines en las columnas 25 a 39.
- En la protoboard, los 5 agujeros de media columna (a-e o f-j) están unidos entre sí. Cada riel está unido a lo largo.
- Con un solo micrófono, omite el paso 5.

## Materiales

- 1 ESP32 de 30 pines, 2 micrófonos INMP441, 1 protoboard de 830 puntos
- 5 a 7 cables macho-macho, 12 cables macho-hembra de 10 cm
- 2 capacitores cerámicos de 100 nF (marcados 104), 1 cable micro-USB de datos
- Cautín y estaño (si los micrófonos traen los pines sueltos), multímetro (opcional)

## Paso 1: Soldar los pines de los micrófonos

Si ya vienen soldados, salta este paso.

- [ ] Los pines salen por la cara del chip; la cara con el agujero abierto queda arriba. Pincha las tiras en la protoboard, pon el micrófono encima y suelda los 6 pines de cada micrófono.
- [ ] Ningún punto de estaño toca al pin vecino y el agujero queda limpio.

## Paso 2: Colocar el ESP32

- [ ] Protoboard horizontal: columna 1 a la izquierda, fila a arriba.
- [ ] ESP32 con los componentes hacia arriba y el USB hacia la derecha, sobre la canaleta, de la columna 25 a la 39 (pines en las filas b e i).
- [ ] Presiona por los bordes, no sobre el chip, hasta que entre completo.

| Pin | Queda en | Agujero libre para su cable |
| --- | --- | --- |
| 3V3 | b39 | a39 |
| GND | i38 | j38 |
| D26 | i33 | j33 |
| D25 | i32 | j32 |
| D33 | i31 | j31 |
| VIN | i39 | No usar |

## Paso 3: Alimentación y nodos (cables macho-macho)

| Desde | Hasta | Color |
| --- | --- | --- |
| a39 (3V3) | Riel + de abajo | Rojo |
| j38 (GND) | Riel − de abajo | Negro |
| j33 (D26) | f15, nodo SCK | Amarillo |
| j32 (D25) | f18, nodo WS | Verde |
| j31 (D33) | f21, nodo SD | Azul |

- Si la línea roja o azul de los rieles de abajo se interrumpe a la mitad, une las dos mitades: rojo de + a +, negro de − a −.
- Rotula con cinta las columnas 15, 18 y 21 como SCK, WS y SD.

## Paso 4: Micrófono 1, voz (cables macho-hembra)

| Pin del micrófono | Hasta | Color |
| --- | --- | --- |
| VDD | Riel + | Rojo |
| GND | Riel − | Negro |
| L/R | Riel − (canal izquierdo) | Negro |
| SCK | g15 | Amarillo |
| WS | g18 | Verde |
| SD | g21 | Azul |

- Capacitor de 100 nF: una pata en el riel + y la otra en el riel −, junto a VDD y GND de este micrófono. No tiene polaridad.
- Fija el micrófono con cinta por el borde, sin tapar el agujero.

## Paso 5: Micrófono 2, ruido (cables macho-hembra)

| Pin del micrófono | Hasta | Color |
| --- | --- | --- |
| VDD | Riel + | Rojo |
| GND | Riel − | Negro |
| L/R | Riel + (canal derecho) | Rojo |
| SCK | h15 | Amarillo |
| WS | h18 | Verde |
| SD | h21 | Azul |

- Segundo capacitor de 100 nF entre riel + y riel −, junto a VDD y GND de este micrófono.
- Sepáralo al menos 10 cm del micrófono 1. Sus cables pueden pasar por encima del ESP32.

## Paso 6: Revisión antes de conectar el USB

- [ ] Nada conectado a VIN.
- [ ] Ningún cable entre el riel + y el riel −; entre ellos solo van los capacitores.
- [ ] VDD de los dos micrófonos en +, GND en −.
- [ ] L/R del micrófono 1 en −; L/R del micrófono 2 en +.
- [ ] Columnas 15, 18 y 21 con 3 cables cada una, en la mitad de abajo.
- [ ] Ningún cable flojo y ningún conector hembra tocando a otro.
- [ ] Multímetro en continuidad entre + y −: no hay pitido continuo. Un pitido corto al inicio es normal por los capacitores.

## Paso 7: Conectar el USB

- [ ] Al conectar el USB enciende el LED rojo del ESP32.
- [ ] Nada se calienta. Si algo calienta, desconecta y vuelve al paso 6.
- [ ] Entre el riel + y el riel − hay de 3.2 a 3.4 V. Si hay unos 5 V, algo está en VIN.
- [ ] En Administrador de dispositivos, Puertos (COM y LPT), aparece CP210x o CH340. Si no aparece, cambia el cable USB o instala ese driver.

## Para las pruebas de ruido

- Mueve los micrófonos solo con el USB desconectado.
- Micrófono 1 cerca de la boca, con el agujero hacia ti. Micrófono 2 a 5-10 cm o más, mirando al lado contrario.
- Cables de señal (SCK, WS, SD) de 20 cm o menos.

## Si algo falla

| Síntoma | Revisa |
| --- | --- |
| LED apagado | Cable USB; cortocircuito entre + y − |
| Algo se calienta | VDD y GND invertidos, o algo en VIN |
| No aparece el puerto COM | Cable solo de carga; driver CP210x o CH340 |
| La placa no se deja programar | Nada debe ir en D2, D12 ni D15 |
| Micrófonos mezclados en un canal | Los dos L/R están en el mismo riel |
| Zumbido o chasquidos | Cables largos o flojos; falta un capacitor |
| No queda agujero libre a un lado del ESP32 | Usa dos protoboards, una fila de pines en cada una |

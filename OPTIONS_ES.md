# EDOPro HD Pics Downloader — Opciones y uso con Python

[Read in English](OPTIONS.md)

[¿No tienes Python instalado?](PYTHON_INSTALL_ES.md)

## Paso a paso (Python)
1. Descarga el archivo del script.
   ![Archivo descargado](asset/archivo-descargado.png)
2. Abre una Terminal en la carpeta donde está el script.
   ![Abrir en terminal](asset/abrir-en-terminal.png)
3. Ejecuta el script con Python.
   ![Iniciar script](asset/iniciar-script.png)
4. Espera a que se abra la interfaz en el navegador.
   ![Programa iniciado](asset/programa-iniciado.png)
5. (Opcional) Usa **Vista previa** y luego pulsa **Iniciar**.
   ![Descargando](asset/descargando.png)
6. Al finalizar verás el estado final.
   ![Descarga finalizada](asset/descarga-finalizada.png)
7. Los reportes se guardan junto al script.
   ![Reportes](asset/reportes.png)

## Opciones
- **Carpeta pics**: ruta exacta a `pics` de ProjectIgnis/EDOPro.
- **Forzar reemplazo**: vuelve a descargar todo.
- **Solo faltantes**: descarga solo archivos que no estén.
- **Validar existentes**: re‑descarga imágenes corruptas.
- **Concurrencia**: descargas en paralelo.
- **Reintentos**: intentos por imagen.
- **Timeout (s)**: tiempo máximo por imagen.
- **Máx KB/s**: límite por descarga (0 = sin límite).
- **Filtro tipo**: filtra por tipo (ej. `Spell`, `Monster`, `Trap`).
- **Filtro set**: filtra por set/código (ej. `LOB (Legend of Blue Eyes White Dragon)`, `SDY (Starter Deck: Yugi)`).

## Botones
- **Vista previa**: muestra cuántas imágenes se descargarán.
- **Iniciar**: comienza la descarga.
- **Pausar/Reanudar**: pausa sin cancelar.
- **Cancelar**: detiene la descarga.

## Reportes
Se guardan junto al script en `reports-reportes/`:
- `edopro_download_report_YYYYMMDD_HHMMSS.json`
- `edopro_download_report_YYYYMMDD_HHMMSS.md`

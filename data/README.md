# Catálogo EasyWays — estructura de datos

Este directorio alojará las recetas de Chile y Argentina en un formato independiente de la interfaz.

## Campos previstos
- `id`: identificador estable por fuente y receta.
- `title`: título original.
- `country`: `CL` o `AR`.
- `machine`: modelo de máquina.
- `source_url`: enlace a la ficha oficial.
- `ingredients`: nombres normalizados al español de Chile.
- `original_ingredients`: ingredientes tal como aparecen en la fuente, cuando estén disponibles.
- `published_minutes`: duración indicada por la fuente, no necesariamente tiempo total.
- `uses_oven`: `true`, `false` o `null` cuando no se haya verificado.
- `first_seen`: primera fecha en que nuestro importador detectó la ficha.

## Importante
La web publicada aún utiliza los datos incorporados dentro de `index.html`. Este directorio es una preparación para una importación futura; **no implica que haya sincronización automática funcionando**. La extracción debe respetar las condiciones y restricciones de cada sitio. No se deben inventar ingredientes, tiempos ni uso de horno.

# Application Best Practices - RocotoClip Mundial

Este conjunto de reglas define los estándares de oro para el desarrollo de RocotoClip, asegurando que cada componente sea de nivel "Enterprise" y "Clase Mundial".

## 1. Resiliencia y Experiencia de Usuario (No a los Errores en Crudo)
- **Error Boundaries:** Nunca permitas que una excepción no capturada llegue al usuario. Debes usar "Error Boundaries" en React y bloques `try/catch` globales en el servidor.
- **UI de Error:** Si algo falla, muestra un mensaje amigable con una opción de "Reintentar" o "Contactar Soporte".
- **Feedback Constante:** El usuario siempre debe saber qué está haciendo el sistema (barra de carga, mensajes de estado).

## 2. Seguridad de Nivel Bancario (Multi-usuario)
- **Aislamiento Total de Datos (RLS):** Cada consulta a la base de datos DEBE pasar por las políticas de Row Level Security de Supabase. El código del servidor nunca debe consultar tablas sin filtrar por `user_id` a menos que sea una operación administrativa crítica.
- **Protección de Secretos:** Las claves `Service Role` de Supabase JAMÁS deben llegar al frontend. El frontend solo usa la `Anon Public Key`.
- **Ofuscación de Errores Técnicos:** NUNCA mostrar mensajes de error crípticos, trazas de stack, nombres de bases de datos o detalles de APIs (como "Forbidden use of secret API key") al usuario final. Estos mensajes dan información valiosa a atacantes. En su lugar, mostrar mensajes genéricos y amigables como "Ha ocurrido un error en la conexión. Por favor, intenta de nuevo en unos minutos". Los detalles técnicos deben guardarse solo en logs internos del servidor.
- **Validación Estricta:** Implementar esquemas de validación (Zod en TS, Pydantic en Python) para cada entrada de usuario, evitando inyecciones o datos corruptos.

## 3. Escalamiento elástico (World-Class Scale)
- **Arquitectura de Micro-servicios:** El backend (FastAPI) y el procesamiento de video (Orquestador) deben estar desacoplados para que podamos escalar los trabajadores de video de forma independiente.
- **Manejo de Concurrencia:** Utilizar bloqueos (`Lock`) y semáforos en procesos compartidos para evitar "deadlocks" cuando múltiples usuarios procesen videos simultáneamente.
- **Infraestructura Cloud:** Preferir soluciones "Serverless" o de contenedores que permitan subir de capacidad sin tiempo de inactividad.

## 4. Eficiencia y Rendimiento Extremo
- **Optimización de Recursos:** El procesamiento de video (FFmpeg, MediaPipe) es costoso. Debemos optimizar cada paso (resize de frames, selección de puntos clave) para reducir el uso de CPU/GPU.
- **Carga Diferida y SSR:** En el frontend, usar Server Components (Next.js) para reducir el tiempo de primera carga y "Lazy Loading" para componentes pesados (Remotion).
- **Caché Inteligente:** Implementar capas de caché para resultados de búsqueda viral y transcripciones frecuentes para ahorrar llamadas a APIs costosas (Gemini).

## 5. Observabilidad (Logs Quirúrgicos)
- **Ciclo de Vida del Proceso:** Cada tarea debe registrar:
  - `[START]`: Cuándo y quién inicia.
  - `[PROGRESS]`: Hitos clave de la tarea.
  - `[END]`: Tiempo total y resultado.
  - `[ERROR]`: Stack trace completo y contexto del error.
- **Auditoría:** Todo cambio significativo debe quedar registrado para debugging e histórico del usuario.

## 6. Integración (Antigravity & Stitch)
- **Diseño Premium:** Utiliza `StitchMCP` para cada nueva UI, asegurando que se mantenga el estilo "Glassmorphism" y estético en toda la app.
- **Refactorización Continua:** Si una función crece demasiado, divídela en micro-servicios o utilitarios reutilizables.

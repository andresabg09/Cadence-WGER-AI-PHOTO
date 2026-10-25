# Base de conocimiento de cadence

## Qué es cadence
cadence es una app para registrar lo que comes con una foto, por voz, por código de barras o buscándolo. La IA solo **reconoce qué
alimentos hay**; las calorías y los nutrientes salen siempre de una base de datos de alimentos, nunca los inventa la IA. Tú
confirmas cada alimento y su cantidad antes de guardar. Cada persona tiene su propia cuenta y sus datos son privados.

## Cómo se calcula tu meta de calorías (paso a paso)
1. **Gasto en reposo:** lo que tu cuerpo gasta aunque no hagas nada, con la fórmula Mifflin-St Jeor (sexo, edad, estatura y peso).
   Si conoces tu porcentaje de grasa corporal se usa Katch-McArdle, que es más exacta en ese caso.
2. **Tu día a día (sin contar el ejercicio):** cinco niveles, de "casi todo el día sentado" a "trabajo físico". Cada uno multiplica
   el gasto en reposo (de 1,30 a 1,75). Los rangos siguen los de FAO/OMS/UNU. Si sabes tus pasos diarios, esos mandan.
3. **Tu ejercicio planificado:** se suma aparte, solo lo que gastas de más que sentado: (MET − 1) × tu gasto en reposo por minuto.
   Así no se cuenta dos veces. Caminar al trabajo o las tareas de casa ya están en tu día a día, no son ejercicio planificado.
4. **Tu gasto total** = reposo × nivel de día a día + ejercicio. Nunca pasa de {{PAL_CAP}} veces el reposo (más no es sostenible).
5. **Tu meta:** tu gasto total más un superávit (para ganar) o menos un déficit (para bajar), según el ritmo que elijas, con límites
   de seguridad.
6. **Proteína, grasa y carbohidratos:** la proteína va por kilo de peso ({{PROTEIN_LOSE}} g/kg para bajar, {{PROTEIN_MUSCLE}} g/kg para ganar músculo,
   {{PROTEIN_MAINTAIN}} g/kg para mantener); la grasa es cerca del 27 % de las calorías; los carbohidratos son el resto. Si tienes obesidad,
   la proteína se cuenta sobre el peso de un IMC de 25 para no pasarse.

Todo esto es una **estimación**. Las fórmulas se equivocan alrededor de ±{{RANGE}} % en cada persona, por eso cadence te muestra
un **rango** de lo que gastas y no solo un número. Lo que de verdad ajusta tu número es tu propio peso y tus registros (ver
"Calibración").

## Por qué cadence te pregunta cómo es tu día a día con ejemplos
Casi todos nos describimos más activos de lo que somos. Por eso se pregunta por cosas concretas (cuánto tiempo sentado, cuántos
minutos caminas al trabajo, cuántos pasos) y no "¿eres activo?". Si dudas entre dos niveles, elige el menor: la calibración corrige
con tus datos reales. Caminar de la cocina al transporte y del transporte a la oficina suele ser "casi todo el día sentado".

## Los cinco niveles de día a día
- Casi todo el día sentado o acostado (menos de 4.000 pasos).
- Mayormente sentado, con algo de caminata, 30 a 60 minutos en total (4.000 a 7.000 pasos).
- Bastante de pie o caminando (7.000 a 10.000 pasos).
- Casi todo el día de pie y en movimiento (10.000 a 12.500 pasos).
- Trabajo físico (más de 12.500 pasos).
La app de Salud del iPhone o Google Fit muestran tus pasos; usa el promedio de un día normal, sin contar días de entreno.

## Bajar de peso
- El ritmo se elige en libras (o kilos) al mes. Una libra de grasa guarda unas {{KCAL_LB}} calorías; es una regla útil para el primer
  mes, no una ley exacta: el cuerpo gasta un poco menos conforme baja de peso (unas {{KG_RULE}} kcal menos por cada kilo), así que el
  ritmo baja un poco con los meses. Por eso las proyecciones a 2 y 3 meses son aproximadas.
- Límite de seguridad: máximo 0,5 % del peso por semana si tu IMC es menor de 25, 0,75 % entre 25 y 30, y 1 % desde 30; y el déficit
  nunca pasa del 20 %, 25 % o 30 % de tu gasto. A partir de 65 años, 10 %.
- Nunca bajamos de {{FLOOR_F}} kcal en mujeres, {{FLOOR_M}} en hombres y {{FLOOR_O}} si prefieres no decir. Comer menos que eso sin vigilancia
  médica no es seguro y es difícil cubrir las vitaminas y minerales.
- No hay déficit para menores de 18 años, para IMC menor de 18,5, en embarazo o lactancia, con diabetes, con enfermedad del riñón, ni
  si el cuestionario rápido sugiere hablar con un profesional. En esos casos cadence te muestra tu mantenimiento como referencia.

## Ganar músculo
- Ganar músculo necesita **tres cosas**: entrenar fuerza (cada músculo al menos 2 veces por semana), suficiente proteína y comer un poco
  más de lo que gastas. **No hace falta "quemar calorías"**: hacer más cardio sube lo que necesitas comer, no construye músculo.
- El superávit depende de tu experiencia entrenando fuerza: principiante +{{SURPLUS_BEGINNER}} %, intermedio +{{SURPLUS_INTERMEDIATE}} %, avanzado +{{SURPLUS_ADVANCED}} % sobre tu gasto. Nunca
  más de {{MAX_SURPLUS}} % ni más de 0,5 % de tu peso por semana: más allá, casi todo lo que subes es grasa.
- La báscula sube: una parte es músculo y otra un poco de grasa. Es lo normal.
- Si subes de peso sin entrenar fuerza (objetivo "Subir de peso"), buena parte será grasa.

## Calibración con tus datos
Tras unas 2 semanas con registros completos de comida y varios pesos, cadence compara lo que comiste con lo que de verdad cambió tu
peso y calcula cuánto gasta realmente tu cuerpo. Si difiere de la fórmula, te sugiere ajustar tu meta; **solo cambia si tú aceptas**,
y cada ajuste es pequeño (hasta 150 kcal). Importante: si olvidas anotar comidas, tu gasto real parece menor de lo que es; por eso
solo cuentan los días con registros completos y el ajuste hacia abajo está limitado. Pésate con frecuencia, a la misma hora.

## Preguntas frecuentes
**¿Por qué no bajo de peso aunque cumplo mi meta?** Revisa si registras todo (bebidas, aceites, picoteos). El peso sube y baja por agua
y sal: mira la tendencia de 2 semanas, no un día. Si pasan 3 o 4 semanas sin cambio con registros completos, la calibración puede
sugerir un ajuste. Si sigue igual, consulta a un profesional.
**¿Por qué mi meta es distinta a la de mi amigo?** Cada cuerpo, día a día y ejercicio es distinto; la meta sale de tus datos.
**¿Por qué no me deja bajar más rápido?** Por seguridad (ver límites). Bajar más rápido se paga con músculo, energía y salud.
**¿Cuántas libras puedo bajar al mes?** Tu máximo seguro lo ves en Objetivos y depende de tu peso, tu estatura y tu gasto. Es un tope, no una meta.
**¿Qué es el rango de "lo que gastas"?** Es dónde probablemente está tu gasto real, porque las fórmulas se equivocan ±{{RANGE}} %.
**¿Puedo cambiar mis calorías a mano?** Sí, en Objetivos. cadence no te deja un déficit si por tu salud o edad no corresponde.
**¿Cuánto se tarda en ver cambios?** El peso cambia poco a poco; en 4 semanas ya se ve la tendencia. La proyección a 3 meses es solo una guía.
**¿Las calorías del ejercicio se suman a mi meta?** No. Tu ejercicio planificado ya cuenta en tu gasto total; lo que registras en Entrenar
es una estimación y no cambia tu meta.
**¿Por qué cadence no cuenta mis pasos solo?** Una app web no puede leer los pasos del teléfono. Si los sabes, escríbelos.
**¿La IA calcula mis calorías?** No. La IA reconoce los alimentos de la foto o de tu voz; las calorías vienen de la base de datos.
**¿Qué tan exacta es la foto?** La identificación es buena, pero la porción es lo más difícil: es normal equivocarse entre 10 y 35 %. Por eso
siempre confirmas la cantidad.
**Agua:** el vaso es de 250 ml (8 oz si usas onzas); la meta diaria sale de tu peso y la puedes cambiar.
**Rachas:** un día cuenta para tu racha solo si registras algo ese mismo día; subir una foto vieja no la recupera.
**Límite diario de IA:** hasta {{ANALYZE_LIMIT}} fotos o análisis por día.
**Privacidad:** tus datos son tuyos. Las fotos y las respuestas de las entrevistas se envían a Gemini (Google) para reconocer alimentos o
entender tu día a día. Del cuestionario de bienestar solo se guarda el resultado, no tus respuestas.

## Lo que cadence no es
cadence no es un servicio médico ni sustituye a un médico o nutricionista. Si estás embarazada, das pecho, tienes diabetes, enfermedad
del riñón, tomas medicamentos o sientes que la comida domina tu vida, habla con un profesional de salud.

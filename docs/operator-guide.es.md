# Guía del operador

*[English version](operator-guide.en.md)*

Eres la persona responsable de un agente de inteligencia artificial. El agente tiene una página web pública que funciona como su **carné de identidad**: dice que es una IA, qué tecnología usa, qué no hará nunca y quién responde por él, que eres tú.

El agente se encarga de casi todo. Tú solo haces dos cosas: **una preparación inicial** y, cada vez que cambie algo, **leer y firmar una declaración**. No necesitas saber programar ni usar git.

## Preparación inicial (una sola vez)

1. **Ten una clave OpenPGP.** Es tu firma digital personal. Si no tienes una, créala con la herramienta que prefieras: Kleopatra (Windows), GPG Suite (Mac) o GnuPG (Linux).
2. **Dale al agente tu clave pública.** Es un bloque de texto que empieza por `-----BEGIN PGP PUBLIC KEY BLOCK-----`. Es pública: puedes enviarla por cualquier canal. **Nunca le des tu clave privada.**
3. **Decide dónde se publica la web** (por ejemplo, GitHub Pages con tu dominio) y dale al agente el acceso que necesite para publicar allí.
4. **Prepara el entorno del agente**, si el agente no puede hacerlo solo:
   - una carpeta donde guardar sus datos de forma permanente;
   - una frase de paso para sus claves, guardada como secreto de su configuración (nunca dentro de esa carpeta).
5. **Crea un registro DNS** en tu dominio. Tras la primera publicación, el agente te dirá exactamente cuál. Contiene la huella de tu clave y no tendrás que volver a tocarlo.

## Cada vez que algo cambie

### 1. Recibirás una declaración

Es un texto como este:

```
OPERATOR DECLARATION · NorAI · no. 2 · 25 October 2026

I, Jonathan, am the person responsible for the AI agent NorAI.
I declare that the information published at https://norai.si/ is correct:

  What it is:       Personal AI agent: an artificial intelligence system, not a person.
  On whose behalf:  Its operator only
  Technology:       Hybrid, local-first: ~90% local models, ~10% cloud (Anthropic, OpenAI)
  ...
  Valid until:      2027-10-25

Changes since declaration no. 1:
  - Added Anthropic as a cloud provider.

────────────── Technical annex (checked by machines) ──────────────
agent: NorAI
...
```

La declaración puede estar en inglés o en español: el agente usa el idioma que tenga configurado para ti.

### 2. Léela antes de firmar

Comprueba la parte de arriba, la que está escrita en lenguaje normal:

- ¿Es **verdad** todo lo que dice sobre el agente?
- ¿Los **cambios** son los que esperabas? Si aparece un cambio que no conoces, pregunta antes de firmar.
- ¿El **número** sigue al de la última declaración que firmaste?
- ¿La **fecha de validez** es razonable?

El anexo técnico no necesitas entenderlo. Sirve para que los programas comprueben que la web publicada es exactamente la que tú has aprobado.

### 3. Fírmala

Firma el texto **exactamente como te llegó**, sin cambiar nada, con tu herramienta habitual. Valen dos formas:

- **Texto firmado** (en Kleopatra: "Firmar"; en GnuPG: `gpg --clearsign`). Devuelve un texto que empieza por `-----BEGIN PGP SIGNED MESSAGE-----`.
- **Firma separada** (un fichero `.asc` o `.sig` junto al texto).

### 4. Devuélvesela al agente

Envía lo que haya generado tu herramienta por el canal que uséis normalmente. La firma no es secreta: no pasa nada si alguien más la ve.

El agente comprobará que la firma es tuya y que corresponde exactamente a esa declaración. Después publicará la web y te avisará.

## Si algo no está bien

**No firmes.** Dile al agente qué hay que corregir. Preparará una declaración nueva y te la enviará. Sin tu firma, el agente no publica nada.

## Lo que significa tu firma

Con tu firma declaras que la información publicada sobre el agente es correcta y que tú eres la persona responsable de él. Cualquiera puede comprobar en la web que la firma es tuya, que cubre exactamente lo que se ve publicado y que forma parte de una cadena con todas tus declaraciones anteriores.

## Si pierdes tu clave o te la roban

Avisa al agente. Tendrás que crear una clave nueva, revocar la antigua con tu herramienta, darle al agente la nueva clave pública y actualizar el registro DNS. El agente te enviará entonces una declaración nueva para firmar con la nueva clave.

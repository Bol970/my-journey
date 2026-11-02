# Этап 1. Фундамент: шифрование, хранилище, синхронизация. План реализации

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Зашифрованная запись с фото создаётся на Android, появляется в браузере, правится там и возвращается на телефон. Фоновая отправка с телефона переживает блокировку дневника, обрыв сети и перезагрузку.

**Architecture:** Общий TypeScript-код (`src/core`) отвечает за формат шифрования, модель записей, локальное хранилище, приём изменений и разрешение конфликтов. Он работает в браузере и в WebView Capacitor. **Облако подключается как плагин** `StorageBackend`: синхронизация знает только объекты с ключами (загрузить идемпотентно с докачкой, проверить наличие, список, изменения по курсору, скачать). В этом этапе один плагин, `gdrive` (Google Drive, `appDataFolder`), и поддельный плагин для тестов. Вся информация для синхронизации (граф версий, признак удаления) записана в ключе объекта, поэтому будущим плагинам (WebDAV и др.) нужны только имена файлов. Отправка идёт через интерфейс `Uploader`: в браузере его реализует TypeScript-цикл, на Android Kotlin-очередь с WorkManager, которая работает только с шифротекстом и вызывает Kotlin-часть плагина. Каждая версия записи хранится отдельным неизменяемым объектом, конфликты видны как несколько «голов». Локальный дневник привязан к хранилищу через объект ключей `kr/<keyId>`: перед любой отправкой и приёмом проверяется, что он есть в подключённом хранилище. Операции над одной записью выполняются строго по очереди, а в браузере дневник открыт только в одной вкладке.

**Tech Stack:** React, TypeScript, Vite, Vitest, Tiptap (StarterKit), `idb`, `fake-indexeddb`, `node:sqlite` (только в тестах), Capacitor (Android), `@capacitor-community/sqlite`, Kotlin, WorkManager, OkHttp (+ MockWebServer в тестах), Google Play services Identity (`AuthorizationClient`), Google Identity Services (веб), Drive REST API v3.

**Spec:** `docs/superpowers/specs/2026-11-02-my-journey-design.md`. Исполнитель читает его целиком вместе с этим планом и с `AGENTS.md`.

## Global Constraints

- Язык интерфейса русский. Строки интерфейса лежат в `src/ui/strings.ts`.
- Android: `minSdkVersion 30`. Идентификатор пакета `io.github.bol970.myjourney` **[решение исполнителя]**: в стиле проектов с GitHub, без личного домена. Название приложения «Мой дневник».
- Веб: адрес строго `http://localhost:4173`, сервер слушает только `127.0.0.1` (`vite preview --host 127.0.0.1 --port 4173 --strictPort`).
- Хранилище: только через интерфейс `StorageBackend` (Task 5). Код вне `src/core/storage/<плагин>/` и Kotlin-пакета `storage/<плагин>` не знает про конкретное облако. Плагин `gdrive`: единственная область доступа `https://www.googleapis.com/auth/drive.appdata`, все файлы лежат в `appDataFolder`, имя файла равно ключу объекта.
- **Схема ключей объектов, версия 1** (часть формата данных, одинакова для всех плагинов): `kr/<keyId>` файл ключей (JSON); `ev/<entryId>/<versionId>.<l|t>[.<parentId>]…` версия записи (`l` живая, `t` в корзине, родителей от 0 до 4); `ao/<attachmentId>` оригинал вложения. Разделитель `.` не входит в алфавит base64url, поэтому разбор однозначен. Наибольшая длина ключа около 150 символов.
- Шифрование: AES-256-GCM. Ключ дневника 32 случайных байта. Пароль превращается в ключ через PBKDF2-HMAC-SHA-256, **600 000 итераций**, соль 16 байт. Блок потокового шифрования **1 МиБ (1 048 576)**. Каждый поток (вложение) шифруется своим ключом: HKDF-SHA-256 от ключа дневника со случайной солью 16 байт.
- Открыто в хранилище только то, что есть в ключах объектов: идентификаторы, родители версии, признак удаления, идентификатор ключа дневника. Время сохранения и устройство лежат внутри шифротекста.
- Идентификаторы записей, версий, вложений и устройств: 16 случайных байт в base64url без паддинга (22 символа). Идентификатор ключа: 8 случайных байт в hex (16 символов).
- Номера форматов: файл ключей `format: 1`, магия запечатанного объекта `MJ1S`, магия потока `MJ1C`, содержимое записи `schema: 1`.
- Загрузка на Android: записи уходят при любой сети, вложения только по Wi-Fi (`UNMETERED`), пока не включён переключатель мобильной сети.
- Инструменты: Gradle и Android SDK запускаются только в Docker-образе с Docker Hub через `docker/gradle.sh`, кэш Gradle лежит в томе Docker `mj-gradle`. Node 22 и Java 21 локальные. В систему ничего не ставить. `adb`: `~/Android/Sdk/platform-tools/adb`.
- Секреты: OAuth client ID лежат в `.env.local` (в git не попадает). Ключ подписи хранится в `~/.config/my-journey/`, пароли в `secret-tool`. Секреты не печатать.
- Git: репозиторий **публичный** (`github.com/Bol970/my-journey`). Коммит в конце каждой задачи, push по просьбе владельца. Сообщения коммитов пишутся по-русски, без `Co-Authored-By`. **Перед каждым коммитом** проверить `git diff --cached --stat` и содержимое: в индекс не должно попасть ничего из `private/`, `.env.local`, ключей и личных данных владельца (устройства, пути, сетевое хранилище, состав архива, названия его тегов).
- Архив Journey на этом этапе не нужен. Тексты записей из него не читать.

## Review Focus

1. **Приложение убили посреди набора текста.** После перезапуска набранное на месте (черновик сохраняется до запечатывания версии). Тест: Task 9 `черновик переживает новый экземпляр Diary`.
2. **Токен Google истёк посреди загрузки большого файла.** Элемент очереди остаётся в ожидании, смещение не теряется, после переподключения загрузка продолжается. Тест: Task 7 `ошибка авторизации ставит очередь на паузу без потери смещения`.
3. **Обрыв возобновляемой загрузки и перезапуск процесса.** Загрузка продолжается со смещения, которое сообщил Drive, а не с нуля, и без второго файла. Тесты: Task 5 `gdrive: продолжает с серверного смещения после перезапуска` и Task 12 `GoogleDriveBackend продолжает сессию со смещения сервера`.
4. **Повтор страницы изменений или повторный полный листинг.** Дубликатов версий нет. Тест: Task 8 `повторный pull не создаёт дублей`.
5. **Повреждённая версия или неверный пароль.** Повреждённая запись помечена, остальные показываются. Неверный пароль не меняет состояние. Тесты: Task 9 `повреждённая версия помечена, остальные в списке`, Task 3 `неверный пароль даёт WrongSecretError`, Task 10 `неверный пароль не меняет состояние`.

---

### Task 1: Каркас веб-проекта и базовые утилиты

**Files:**
- Create: `package.json`, `tsconfig.json`, `vite.config.ts`, `index.html`, `src/main.tsx`, `src/ui/App.tsx`, `.gitignore`, `.env.example`
- Create: `src/core/bytes.ts`, `src/core/ids.ts`
- Test: `src/core/bytes.test.ts`, `src/core/ids.test.ts`

**Interfaces:**
- Produces:
  - `toB64u(b: Uint8Array): string`, `fromB64u(s: string): Uint8Array`, `utf8(s: string): Uint8Array`, `fromUtf8(b: Uint8Array): string`, `concat(...parts: Uint8Array[]): Uint8Array`, `u32be(n: number): Uint8Array`, `toHex(b: Uint8Array): string`, `fromHex(s: string): Uint8Array`, `randomBytes(n: number): Uint8Array`, `equalBytes(a: Uint8Array, b: Uint8Array): boolean`
  - `newId(): string`, `isId(s: string): boolean`

- [ ] **Step 1: Проверить репозиторий:** `git status` чистый, `private/` в `.gitignore` (см. Global Constraints).
- [ ] **Step 2: Создать каркас.** Последние стабильные версии `react`, `react-dom`, `vite`, `@vitejs/plugin-react`, `typescript`, `vitest`, `fake-indexeddb`, `tsx`. Скрипты в `package.json`: `"dev": "vite --host 127.0.0.1 --port 4173 --strictPort"`, `"build": "tsc --noEmit && vite build"`, `"preview": "vite preview --host 127.0.0.1 --port 4173 --strictPort"`, `"test": "vitest run"`. `.gitignore` (уже создан при заведении репозитория) дополнить: `android/app/build`, `android/.gradle`. В нём уже есть `private/`, `node_modules`, `dist`, `.env.local`, `*.jks`. `.env.example`: `VITE_GOOGLE_WEB_CLIENT_ID=` и `VITE_FAKE_STORAGE=0`.
- [ ] **Step 3: Написать падающие тесты**

```ts
test('base64url туда и обратно без паддинга', () => {
  const b = new Uint8Array([0, 1, 2, 250, 251, 252, 253, 254, 255])
  const s = toB64u(b)
  expect(s).not.toMatch(/[=+/]/)
  expect(fromB64u(s)).toEqual(b)
})
test('u32be', () => expect(u32be(0x01020304)).toEqual(new Uint8Array([1, 2, 3, 4])))
test('hex туда и обратно', () => expect(fromHex(toHex(new Uint8Array([0, 15, 255])))).toEqual(new Uint8Array([0, 15, 255])))
test('newId: 22 символа base64url и уникален', () => {
  const ids = new Set(Array.from({ length: 1000 }, newId))
  expect(ids.size).toBe(1000)
  for (const id of ids) expect(isId(id)).toBe(true)
  expect(isId('abc')).toBe(false)
})
```

- [ ] **Step 4: Запустить** `npx vitest run src/core`. Ожидается FAIL (модулей нет).
- [ ] **Step 5: Реализовать** `bytes.ts` и `ids.ts`. `isId` проверяет `/^[A-Za-z0-9_-]{22}$/`, `randomBytes` использует `crypto.getRandomValues`.
- [ ] **Step 6: Запустить** `npx vitest run src/core && npm run build`. Ожидается PASS, сборка без ошибок.
- [ ] **Step 7: Commit** `Каркас проекта и базовые утилиты`.

---

### Task 2: Запечатанные объекты и потоковое шифрование (TypeScript) + тестовые векторы

**Files:**
- Create: `src/core/crypto/key.ts`, `src/core/crypto/sealed.ts`, `src/core/crypto/stream.ts`, `src/core/crypto/errors.ts`
- Create: `scripts/gen-vectors.ts`, `testdata/vectors/stream-v1.json` (генерируется)
- Test: `src/core/crypto/sealed.test.ts`, `src/core/crypto/stream.test.ts`

**Interfaces:**
- Consumes: Task 1 (`bytes.ts`).
- Produces:
  - `interface DiaryKey { keyId: string; key: CryptoKey; raw: Uint8Array }`, `importDiaryKey(raw: Uint8Array, keyId: string): Promise<DiaryKey>`
  - `class DecryptError extends Error`
  - `seal(k: DiaryKey, context: string, plaintext: Uint8Array, iv?: Uint8Array): Promise<Uint8Array>`, `open(k: DiaryKey, context: string, sealed: Uint8Array): Promise<Uint8Array>`
  - `STREAM_CHUNK = 1048576`, `encryptStream(k: DiaryKey, context: string, source: Blob | Uint8Array, opts?: { chunkSize?: number; salt?: Uint8Array; noncePrefix?: Uint8Array }): AsyncGenerator<Uint8Array>`, `decryptStream(k: DiaryKey, context: string, cipher: Blob | Uint8Array): AsyncGenerator<Uint8Array>`, `decryptAll(k: DiaryKey, context: string, cipher: Blob | Uint8Array): Promise<Uint8Array>`, `encryptedSize(plainSize: number, chunkSize?: number): number`

**Форматы (точно по байтам, Kotlin в Task 11 повторяет их один в один):**
- Запечатанный объект: `"MJ1S"(4) | keyId(8 байт) | iv(12) | шифротекст с тегом(16)`. AAD = первые 12 байт (`magic|keyId`) + `utf8(context)`. Случайный 96-битный IV под ключом дневника допустим: таких объектов (версий записей, черновиков) будут десятки тысяч, что далеко от предела 2^32.
- Поток: заголовок `"MJ1C"(4) | keyId(8) | chunkSize u32be(4) | salt(16) | noncePrefix(7)` = 39 байт. **Ключ потока свой у каждого файла:** `HKDF-SHA-256(ikm = ключ дневника, salt = salt, info = utf8("mj:stream:v1:" + context))`, 32 байта, AES-256-GCM. Без этого все потоки делили бы ключ дневника, а 56 случайных бит префикса nonce слишком мало, чтобы исключить повтор nonce. Затем блоки: блок `i` = GCM(ключ потока, открытый блок `i`) с тегом 16 байт. Nonce = `noncePrefix(7) | u32be(i) | (последний ? 0x01 : 0x00)`. AAD = 39 байт заголовка + `utf8(context)`. Все блоки, кроме последнего, ровно `chunkSize`. Пустой файл даёт ровно один последний блок нулевой длины. Если размер кратен `chunkSize`, последний блок полный, пустой хвостовой блок не добавляется.
- Расшифровка отклоняет: чужую магию, несовпадение `keyId`, поток без последнего блока, данные после последнего блока. Во всех случаях бросается `DecryptError`.
- Контексты на этом этапе: `att:<attachmentId>` (оригинал вложения), версии записи и черновики (Task 4, Task 9).

- [ ] **Step 1: Написать падающие тесты** (в тестах `chunkSize: 64`, чтобы было быстро)

```ts
test('seal/open туда и обратно', async () => { /* open(k,'c',await seal(k,'c',p)) равно p */ })
test('open с другим контекстом → DecryptError', ...)
test('изменённый байт → DecryptError', ...)
test.each([0, 1, 63, 64, 65, 192])('поток туда и обратно, %i байт', async n => { /* decryptAll(encrypt) равно исходным; общая длина равна encryptedSize(n, 64) */ })
test('без последнего блока → DecryptError', ...)
test('блоки переставлены → DecryptError', ...)
test('лишние байты после последнего блока → DecryptError', ...)
test('другой контекст потока → DecryptError', ...)
test('два шифрования одних данных: разные соли, разные шифротексты, оба расшифровываются', ...)
test('векторы stream-v1.json: шифрование с фиксированным noncePrefix даёт cipherHex, расшифровка даёт plainHex', ...)
```

- [ ] **Step 2: Запустить** `npx vitest run src/core/crypto`. Ожидается FAIL.
- [ ] **Step 3: Реализовать** `key.ts`, `sealed.ts`, `stream.ts` на WebCrypto (`crypto.subtle`, ключ потока через `deriveKey` с `HKDF`). `encryptStream` читает `Blob` через `blob.slice()` по `chunkSize`, чтобы не держать файл в памяти целиком.
- [ ] **Step 4: Написать** `scripts/gen-vectors.ts`. Фиксированные ключ, `keyId`, `salt`, `noncePrefix` и контекст `att:vector`. Случаи: 0, 1, 64, 65 и 200 байт при `chunkSize` 64, плюс один случай 1 048 577 байт с настоящим `STREAM_CHUNK`, где открытый текст задан формулой `i % 251`, чтобы не раздувать JSON: поле `plainRule`. Поля случая: `name`, `keyHex`, `keyIdHex`, `context`, `chunkSize`, `saltHex`, `noncePrefixHex`, `plainHex | plainRule`, `cipherSha256` и `cipherHex` (только для маленьких). Запуск: `npx tsx scripts/gen-vectors.ts`.
- [ ] **Step 5: Запустить** `npx tsx scripts/gen-vectors.ts && npx vitest run src/core/crypto`. Ожидается PASS.
- [ ] **Step 6: Commit** `Формат шифрования объектов и потоков, тестовые векторы`.

---

### Task 3: Ключи дневника: пароль и ключ восстановления

**Files:**
- Create: `src/core/crypto/recovery.ts`, `src/core/crypto/keyring.ts`
- Test: `src/core/crypto/recovery.test.ts`, `src/core/crypto/keyring.test.ts`

**Interfaces:**
- Consumes: Task 2 (`DiaryKey`, `importDiaryKey`).
- Produces:
  - `PBKDF2_ITERATIONS = 600000`
  - `interface Wrap { iv: string; ct: string }` (base64url)
  - `interface KeyringFile { format: 1; keyId: string; kdf: { alg: 'PBKDF2-SHA256'; iterations: number; salt: string }; wraps: { password: Wrap; recovery: Wrap }; createdAt: number }`
  - `class WrongSecretError extends Error`
  - `encodeRecoveryKey(b: Uint8Array): string`, `decodeRecoveryKey(s: string): Uint8Array`
  - `createKeyring(password: string, opts?: { iterations?: number; now?: number }): Promise<{ file: KeyringFile; key: DiaryKey; recoveryKey: string }>`
  - `unlockWithPassword(file: KeyringFile, password: string): Promise<DiaryKey>`, `unlockWithRecovery(file: KeyringFile, recoveryKey: string): Promise<DiaryKey>`

Детали:
- Ключ из пароля: PBKDF2(`utf8(password.normalize('NFC'))`, соль 16 байт, итерации, SHA-256), 256 бит, AES-GCM.
- Ключ восстановления: 32 случайных байта, которые сами используются как AES-ключ обёртки. Записываются в Crockford base32 (алфавит `0123456789ABCDEFGHJKMNPQRSTVWXYZ`), 52 символа, группами по 4 через `-`. При разборе регистр не важен, `-` и пробелы игнорируются, `O` читается как `0`, `I` и `L` как `1`. Неверная длина или неизвестный символ дают `WrongSecretError`.
- Обёртка: AES-GCM(ключ обёртки, iv 12 байт, открытый текст = 32 байта ключа дневника, AAD = `utf8("mj:wrap:v1:" + kind + ":" + keyId)`), где `kind` равен `password` или `recovery`.

- [ ] **Step 1: Написать падающие тесты** (в тестах `iterations: 1000`, кроме одного)

```ts
test('пароль открывает тот же ключ', async () => { /* unlockWithPassword(file,'пароль-1').raw равен key.raw */ })
test('неверный пароль даёт WrongSecretError', ...)
test('ключ восстановления открывает, в т.ч. строчными и с пробелами', ...)
test('неверный ключ восстановления даёт WrongSecretError', ...)
test('подменённый keyId в файле даёт WrongSecretError', ...)
test('ключ восстановления: 13 групп по 4 символа', () => expect(rk).toMatch(/^([0-9A-HJKMNP-TV-Z]{4}-){12}[0-9A-HJKMNP-TV-Z]{4}$/))
test('по умолчанию 600000 итераций', async () => expect((await createKeyring('x'.repeat(8))).file.kdf.iterations).toBe(600000))
test('KeyringFile переживает JSON.stringify/parse', ...)
```

- [ ] **Step 2: Запустить** `npx vitest run src/core/crypto`. Ожидается FAIL.
- [ ] **Step 3: Реализовать** `recovery.ts` и `keyring.ts`.
- [ ] **Step 4: Запустить** `npx vitest run src/core/crypto`. Ожидается PASS.
- [ ] **Step 5: Commit** `Ключи дневника: пароль и ключ восстановления`.

---

### Task 4: Модель записи, версии и их кодирование

**Files:**
- Create: `src/core/model/entry.ts`, `src/core/model/versions.ts`, `src/core/model/codec.ts`, `src/core/model/keys.ts`
- Test: `src/core/model/versions.test.ts`, `src/core/model/codec.test.ts`, `src/core/model/keys.test.ts`

**Interfaces:**
- Consumes: Task 2 (`seal`, `open`, `DiaryKey`).
- Produces:

```ts
interface Place { lat: number; lon: number; label: string }
interface Weather { tempC: number | null; code: number | null; text: string }
interface AttachmentRef { id: string; kind: 'image' | 'video' | 'other'; mime: string; size: number; name: string; width?: number; height?: number }
interface EntryContent { schema: 1; date: string /* локальное 'YYYY-MM-DDTHH:mm:ss' */; tz: string /* IANA */; title: string; doc: unknown /* JSON Tiptap */; tagIds: string[]; mood: 1 | 2 | 3 | 4 | 5 | null; place: Place | null; weather: Weather | null; attachments: AttachmentRef[] }
type VersionState = 'live' | 'trashed'
interface VersionMeta { entryId: string; versionId: string; parents: string[]; state: VersionState }
interface VersionPayload { savedAt: number; deviceId: string; content: EntryContent }   // всё, без чего синхронизация обходится, лежит внутри шифротекста
const MAX_PARENTS = 4
function emptyContent(now: Date, tz: string): EntryContent
function docToPlainText(doc: unknown): string
function versionContext(m: VersionMeta): string             // `ev:${entryId}:${versionId}:${parents.join(',')}:${state}`
// src/core/model/keys.ts — схема ключей объектов v1 (см. Global Constraints)
function versionKey(m: VersionMeta): string                 // `ev/${entryId}/${versionId}.${state === 'live' ? 'l' : 't'}` + parents.map(p => '.' + p).join('')
function parseVersionKey(key: string): VersionMeta | null   // null для чужих и некорректных ключей
function keyringKey(keyId: string): string                  // `kr/${keyId}`
function parseKeyringKey(key: string): string | null        // keyId или null
function attachmentKey(attachmentId: string): string        // `ao/${attachmentId}`
function encodeVersion(k: DiaryKey, m: VersionMeta, p: VersionPayload): Promise<Uint8Array>
function decodeVersion(k: DiaryKey, m: VersionMeta, sealed: Uint8Array): Promise<VersionPayload>
type Resolution = { kind: 'single'; head: VersionMeta } | { kind: 'conflict'; heads: VersionMeta[] }
function resolve(versions: VersionMeta[]): Resolution     // головы = версии, на которые никто не ссылается как на родителя; heads по versionId (порядок по времени Diary наводит после расшифровки)
```

Граф версий открыт (он в ключе объекта), потому что фоновый загрузчик и приём изменений работают без ключа дневника. Подмену ключа объекта ловит AAD через `versionContext`. Время сохранения и устройство лежат внутри шифротекста: спецификация (6.7) требует, чтобы даты были зашифрованы, и так они защищены аутентификацией GCM.

- [ ] **Step 1: Написать падающие тесты**

```ts
test('линейная история → single, голова = версия без потомков', ...)
test('развилка → conflict с двумя головами', ...)
test('версия-слияние с parents [a,b] → single', ...)
test('потомок пришёл раньше родителя → single', ...)
test('encode/decode туда и обратно, savedAt и deviceId возвращаются из шифротекста', ...)
test('decode с изменёнными parents в meta → DecryptError', ...)
test('versionKey/parseVersionKey туда и обратно для 0, 1 и 4 родителей и обоих состояний', ...)
test('parseVersionKey: чужой префикс, лишние сегменты, неверный id, неизвестное состояние → null', ...)
test('ключ версии не содержит времени и устройства и короче 160 символов', ...)
test('parents больше MAX_PARENTS → ошибка в versionKey', ...)
test('keyringKey/parseKeyringKey и attachmentKey', ...)
test('docToPlainText собирает текст абзацев через пробел', ...)
```

- [ ] **Step 2: Запустить** `npx vitest run src/core/model`. Ожидается FAIL.
- [ ] **Step 3: Реализовать.** `emptyContent` берёт `date` из локального времени `now` в поясе `tz` (через `Intl.DateTimeFormat` с `timeZone`), `doc` равен `{ type: 'doc', content: [] }`.
- [ ] **Step 4: Запустить** `npx vitest run src/core/model`. Ожидается PASS.
- [ ] **Step 5: Commit** `Модель записи и версий`.

---

### Task 5: Хранилище-плагин: общий интерфейс, плагин Google Drive, поддельное хранилище

**Files:**
- Create: `src/core/storage/types.ts`, `src/core/storage/registry.ts`, `src/core/storage/contract.ts`, `src/core/storage/fake-backend.ts`
- Create: `src/core/storage/gdrive/drive-api.ts`, `src/core/storage/gdrive/fake-drive.ts`, `src/core/storage/gdrive/backend.ts`
- Test: `src/core/storage/fake-backend.test.ts`, `src/core/storage/gdrive/drive-api.test.ts`, `src/core/storage/gdrive/backend.test.ts`

**Interfaces:**
- Produces, общий контракт (`src/core/storage/types.ts`, `registry.ts`):

```ts
interface ObjectInfo { key: string; size: number; ref?: string /* внутренний id объекта у плагина, у gdrive это id файла */ }
type UploadSource = { kind: 'bytes'; data: Uint8Array } | { kind: 'blob'; blob: Blob }
type UploadState = Record<string, unknown>   // непрозрачное состояние плагина между попытками; очередь хранит его и возвращает как есть
interface Change { object: ObjectInfo; removed: boolean }
interface StorageBackend {
  readonly kind: string                      // 'gdrive'; позже 'webdav', 'yadisk' и т. д.
  upload(key: string, source: UploadSource, size: number, state: UploadState, persist: (s: UploadState) => Promise<void>): Promise<ObjectInfo>
    // идемпотентно по key: повтор с сохранённым state после любого сбоя продолжает загрузку или признаёт её завершённой;
    // второй объект с тем же key не появляется; persist вызывается перед каждым внешним шагом, который нельзя повторить вслепую
  stat(key: string): Promise<ObjectInfo | null>
  list(prefix: string): Promise<ObjectInfo[]>
  changes(cursor: string | null): Promise<{ changes: Change[]; cursor: string }>   // cursor null → весь список как изменения
  download(o: ObjectInfo): Promise<Uint8Array>
}
interface AuthProvider { getToken(): Promise<string> /* без UI; иначе AuthRequiredError */; connect(): Promise<void> /* только из обработчика нажатия */; isConnected(): boolean }
interface StoragePlugin { kind: string; title: string /* «Google Drive» */; auth: AuthProvider; backend: StorageBackend }
class AuthRequiredError extends Error {}; class QuotaError extends Error {}; class TransientError extends Error {}
class IntegrityError extends Error {}        // объект с этим ключом уже есть, но другого размера
function registerStorage(kind: string, factory: (deps: { auth: AuthProvider; fetchImpl?: typeof fetch }) => StoragePlugin): void
function createStorage(kind: string, deps: { auth: AuthProvider; fetchImpl?: typeof fetch }): StoragePlugin   // неизвестный kind → ошибка
function backendContract(name: string, make: () => Promise<StorageBackend & { loseResponse(op: 'upload'): void }>): void   // общий набор тестов для любого плагина
class FakeBackend implements StorageBackend { kind = 'fake'; constructor(opts?: { chunkSize?: number }); failNext(op: keyof StorageBackend, err: Error): void; loseResponse(op: 'upload'): void; objects(): ObjectInfo[]; contentOf(key: string): Uint8Array; calls: { op: string; args: unknown[] }[] }
```

- Produces, плагин `gdrive` (`src/core/storage/gdrive/`): `class GoogleDriveBackend implements StorageBackend { constructor(api: DriveApi, opts?: { smallLimit?: number /* 5 МиБ */; chunkSize?: number /* 8 МиБ, кратно 256 КиБ */ }) }` и регистрация `registerStorage('gdrive', …)` с `title: 'Google Drive'`. Внутренний HTTP-слой плагина:

```ts
interface DriveFile { id: string; name: string; size: number }
interface NewFileMeta { id: string; name: string }
interface DriveChange { fileId: string; removed: boolean; file?: DriveFile }
type ChunkResult = { done: true; file: DriveFile } | { done: false; nextOffset: number }
interface DriveApi {
  generateIds(count: number): Promise<string[]>
  createSmall(meta: NewFileMeta, body: Uint8Array): Promise<DriveFile>          // 409 «уже есть» → возвращает существующий
  startResumable(meta: NewFileMeta, totalSize: number): Promise<{ session: string } | { existing: DriveFile }>   // 409: файл с этим id уже создан
  uploadChunk(session: string, offset: number, chunk: Uint8Array, totalSize: number): Promise<ChunkResult>
  queryResumable(session: string, totalSize: number): Promise<ChunkResult | { expired: true }>
  listAll(): Promise<DriveFile[]>
  startPageToken(): Promise<string>
  listChanges(pageToken: string): Promise<{ changes: DriveChange[]; nextPageToken?: string; newStartPageToken?: string }>
  download(fileId: string): Promise<Uint8Array>
  getFile(fileId: string): Promise<DriveFile | null>                            // 404 → null
  findByName(name: string): Promise<DriveFile[]>                                // все файлы appDataFolder с таким именем
}
class HttpDriveApi implements DriveApi { constructor(getToken: () => Promise<string>, fetchImpl?: typeof fetch) }   // ошибки — общие классы из types.ts
class FakeDrive implements DriveApi { failNext(op: keyof DriveApi, err: Error): void; loseResponse(op: keyof DriveApi): void /* операция выполняется, а вызывающий получает TransientError */; files(): DriveFile[]; contentOf(name: string): Uint8Array; dropSessions(): void; calls: { op: string; args: unknown[] }[] }
```

HTTP (база `https://www.googleapis.com`):
- `generateIds`: `GET /drive/v3/files/generateIds?count=N&space=appDataFolder&type=files`.
- `createSmall`: `POST /upload/drive/v3/files?uploadType=multipart&fields=id,name,size`, `multipart/related`, в метаданных `{ id, name, parents: ['appDataFolder'] }`. На 409 делается `GET /drive/v3/files/{id}?fields=id,name,size`.
- `findByName`: `GET /drive/v3/files?spaces=appDataFolder&q=name='<имя>'&orderBy=createdTime&fields=files(id,name,size)` (кавычки и `\` в имени экранируются).
- `startResumable`: `POST /upload/drive/v3/files?uploadType=resumable` с метаданными и заголовком `X-Upload-Content-Length`, URI берётся из `Location`. На 409 выполняется `getFile(id)` и возвращается `{ existing }`. `getFile`: `GET /drive/v3/files/{id}?fields=id,name,size`, 404 даёт `null`. `uploadChunk`: `PUT` с `Content-Range: bytes start-end/total`. 308 с заголовком `Range: bytes=0-N` даёт `nextOffset = N+1`, 308 без `Range` даёт `nextOffset = 0`, 200/201 означает готово. `queryResumable`: `PUT` с `Content-Range: bytes */total` и пустым телом, 404/410 дают `{ expired: true }`.
- `listAll`: `GET /drive/v3/files?spaces=appDataFolder&pageSize=1000&fields=nextPageToken,files(id,name,size)`, по всем страницам. `listChanges`: `GET /drive/v3/changes?pageToken=…&spaces=appDataFolder&includeRemoved=true&pageSize=1000&fields=nextPageToken,newStartPageToken,changes(fileId,removed,file(id,name,size))`. `download`: `GET /drive/v3/files/{id}?alt=media`.
- Ошибки: 401 → один раз берётся новый токен и запрос повторяется, второй 401 даёт `AuthRequiredError`. 403 с `reason: storageQuotaExceeded` даёт `QuotaError`. 429, 5xx и сетевой `TypeError` дают `TransientError`.

`GoogleDriveBackend` (отображение общего контракта на Drive):
- Объект = файл в `appDataFolder`, `name = key`, `ref` = id файла.
- `upload`, состояние `{ fileId?, session?, offset? }`. Если нет `fileId`, вызвать `generateIds(1)` и **сразу** `persist`. Если размер не больше `smallLimit`, `createSmall` (409 уже обработан в API). Иначе: если нет `session`, `startResumable`. Ответ `existing` значит, что файл уже создан: сверить размер и завершить, при другом размере `IntegrityError`. Иначе `persist({ fileId, session, offset: 0 })`. Если сессия есть, `queryResumable`:
  - `done`: завершить без повторной загрузки (ответ на последнюю часть потерялся);
  - `expired`: `getFile(fileId)`; если файл есть и размер совпадает, завершить, иначе новая сессия с 0;
  - иначе продолжить с `nextOffset`.

  Затем части через `uploadChunk` с `persist` после каждой.
- `stat(key)`: `findByName(key)`, самый ранний файл или `null`. Дубликаты с одним именем допустимы, это последствия повторов: содержимое у них одинаковое.
- `list(prefix)`: `listAll()` с отбором по началу имени.
- `changes(null)`: `startPageToken()`, затем `listAll()` как изменения, курсор = токен. `changes(token)`: `listChanges` по всем страницам, курсор = `newStartPageToken`. Удалённые файлы на этом этапе в изменения не попадают.
- `download(o)`: по `o.ref`, а без него через `stat`.

- [ ] **Step 1: Написать падающие тесты** (поддельный `fetch` записывает запросы)

```ts
test('generateIds запрашивает space=appDataFolder и type=files', ...)
test('createSmall: multipart с id и parents [appDataFolder]', ...)
test('createSmall: 409 → GET существующего файла', ...)
test('uploadChunk: Content-Range bytes 0-262143/1000000; 308 Range bytes=0-262143 → nextOffset 262144', ...)
test('queryResumable: 404 → expired; 200 с файлом → done', ...)
test('startResumable: 409 → existing; getFile: 404 → null', ...)
test('401 дважды → AuthRequiredError; 403 storageQuotaExceeded → QuotaError; 503 → TransientError', ...)
test('listChanges: spaces=appDataFolder и includeRemoved=true', ...)
test('FakeDrive: createSmall дважды с одним id → один файл', ...)
test('FakeDrive: возобновляемая загрузка по частям, после dropSessions → expired', ...)
test('FakeDrive: listChanges после startPageToken видит только новые файлы', ...)
test('FakeDrive.loseResponse: файл создан, а вызывающий получил TransientError', ...)
test('findByName: q=name=… с экранированием кавычек', ...)
// backendContract — запускается для FakeBackend и для GoogleDriveBackend над FakeDrive
test('upload → stat даёт размер, download возвращает те же байты, list(prefix) находит', ...)
test('changes(null) отдаёт всё, changes(cursor) только новое', ...)
test('повтор upload с тем же key и сохранённым state → один объект', ...)
test('loseResponse на upload → повтор с сохранённым state → один объект, загрузка признана завершённой', ...)
test('stat неизвестного ключа → null', ...)
// gdrive/backend.test.ts — особенности Drive
test('gdrive: продолжает с серверного смещения после перезапуска', async () => {
  // smallLimit 1024, chunkSize 262144, данные 600000 байт; failNext('uploadChunk') на второй части;
  // повтор с сохранённым state: содержимое файла равно исходному, первый uploadChunk после повтора с offset 262144
})
test('gdrive: ответ на последнюю часть потерян → queryResumable done → готово без повторной загрузки', ...)
test('gdrive: сессия истекла, а файл уже создан → getFile → готово, файл один', ...)
test('gdrive: сессия истекла (dropSessions), файла нет → заново с 0, файл один', ...)
test('gdrive: TransientError на createSmall → повтор создаёт ровно один файл', ...)
test('gdrive: существующий файл другого размера → IntegrityError', ...)
test('createStorage("gdrive") даёт плагин с title «Google Drive»; неизвестный kind → ошибка', ...)
```

- [ ] **Step 2: Запустить** `npx vitest run src/core/storage`. Ожидается FAIL.
- [ ] **Step 3: Реализовать** общие типы, реестр, `FakeBackend`, `HttpDriveApi`, `FakeDrive` и `GoogleDriveBackend`. `FakeDrive` хранит файлы в памяти, ведёт монотонный журнал изменений для токенов страниц, хранит сессии с полученными байтами, бросает ошибку, заданную через `failNext`, ровно один раз и пишет все вызовы в `calls`. `FakeBackend` грузит частями по `chunkSize` и сохраняет `offset` в `state`, чтобы тесты очереди могли проверить продолжение после перезапуска.
- [ ] **Step 4: Запустить** `npx vitest run src/core/storage`. Ожидается PASS.
- [ ] **Step 5: Commit** `Хранилище-плагин: общий интерфейс и плагин Google Drive`.

---

### Task 6: Локальное хранилище: память, IndexedDB, SQLite

**Files:**
- Create: `src/core/store/types.ts`, `src/core/store/memory.ts`, `src/core/store/indexeddb.ts`, `src/core/store/sqlite.ts`, `src/core/store/contract.ts`, `src/core/store/testing/node-sqlite.ts`
- Test: `src/core/store/store.test.ts`

**Interfaces:**
- Consumes: Task 4 (`VersionMeta`), Task 5 (`ObjectInfo`, `UploadState`).
- Produces:

```ts
interface StoredVersion extends VersionMeta { sealed: Uint8Array; pushed: boolean }
interface StoredDraft { sealed: Uint8Array; rev: number; base: string | null }   // base — локальный id версии, от которой начата правка; хранится открыто, чтобы его можно было менять без ключа
interface LocalStore {
  getMeta<T>(key: string): Promise<T | undefined>; setMeta(key: string, value: unknown): Promise<void>
  putVersion(v: StoredVersion): Promise<boolean>        // false, если versionId уже есть (не перезаписывает)
  hasVersion(versionId: string): Promise<boolean>; versionsOf(entryId: string): Promise<StoredVersion[]>; entryIds(): Promise<string[]>
  markPushed(versionId: string): Promise<void>
  putDraft(entryId: string, d: StoredDraft): Promise<void>; getDraft(entryId: string): Promise<StoredDraft | undefined>
  deleteDraftIfRev(entryId: string, rev: number): Promise<boolean>   // удаляет, только если rev не изменился (атомарно)
  commitSeal(v: StoredVersion, draftRev: number): Promise<'draft-deleted' | 'draft-rebased'>
    // одна транзакция: putVersion(v) и либо удаление черновика (rev совпал), либо draft.base = v.versionId (черновик успели изменить)
  draftIds(): Promise<string[]>
  unpushedVersions(): Promise<StoredVersion[]>
  putRemote(o: ObjectInfo): Promise<void>; remoteByKey(key: string): Promise<ObjectInfo | undefined>   // локальный указатель на объекты хранилища
}
interface BlobStore { putBlob(key: string, data: Blob): Promise<void>; getBlob(key: string): Promise<Blob | undefined>; deleteBlob(key: string): Promise<void> }
interface OutboxItem { key: string; lane: 'entry' | 'attachment'; source: { kind: 'bytes'; data: Uint8Array } | { kind: 'blob'; blobKey: string; size: number }; backendState: UploadState /* {} при постановке */; attempts: number; state: 'pending' | 'done' | 'failed'; lastError?: string; enqueuedAt: number }
interface OutboxStore { addOutbox(i: OutboxItem): Promise<void> /* ключ, который уже есть в любом состоянии, ничего не меняет */; pendingOutbox(): Promise<OutboxItem[]> /* по enqueuedAt */; updateOutbox(key: string, patch: Partial<OutboxItem>): Promise<void>; doneOutbox(): Promise<string[]>; deleteOutbox(keys: string[]): Promise<void> /* done-элементы живут до явного удаления */ }
interface SqlExecutor { run(sql: string, params?: unknown[]): Promise<void>; all<T>(sql: string, params?: unknown[]): Promise<T[]>; transaction(fn: () => Promise<void>): Promise<void> }
class MemoryStore implements LocalStore, BlobStore, OutboxStore
function openIdbStore(dbName: string): Promise<LocalStore & BlobStore & OutboxStore>
function openSqliteStore(db: SqlExecutor): Promise<LocalStore>   // создаёт схему, meta 'schemaVersion' = 1
function storeContract(name: string, make: () => Promise<LocalStore>, reopen?: () => Promise<LocalStore>): void   // общий набор тестов
```

`node-sqlite.ts` реализует `SqlExecutor` поверх `node:sqlite` (`DatabaseSync`) и нужен только для тестов. На Android его заменит адаптер из Task 13.

- [ ] **Step 1: Написать общий набор тестов** `storeContract`: мета-объект туда и обратно; `putVersion` второй раз возвращает `false` и не меняет `sealed`; `versionsOf` и `entryIds`; `markPushed` и `unpushedVersions`; черновики (put, get, list; `deleteDraftIfRev` удаляет только при совпадении `rev` и возвращает `false` иначе; `commitSeal` при совпавшем `rev` сохраняет версию и удаляет черновик, при изменившемся сохраняет версию и переводит `base` черновика на неё; если запись версии падает, черновик не меняется); `remoteByKey`; после `reopen` данные на месте. Отдельно для `MemoryStore` и IndexedDB тесты очереди: `addOutbox` для уже существующего ключа (в том числе `done`) ничего не меняет, `pendingOutbox` по порядку, `updateOutbox` сохраняет `backendState` как есть, `doneOutbox` отдаёт done-элементы, пока их не удалил `deleteOutbox`. Подключить контракт к `MemoryStore`, `openIdbStore` (с `fake-indexeddb/auto`) и `openSqliteStore` (с `node:sqlite`).
- [ ] **Step 2: Запустить** `npx vitest run src/core/store`. Ожидается FAIL.
- [ ] **Step 3: Реализовать** три хранилища. В IndexedDB хранилища `meta`, `versions` (ключ `versionId`, индекс `entryId`), `drafts`, `remote` (ключ `key`), `blobs`, `outbox` (ключ `key`), библиотека `idb`. В SQLite те же таблицы (без `blobs` и `outbox`), `sealed` хранится как BLOB.
- [ ] **Step 4: Запустить** `npx vitest run src/core/store`. Ожидается PASS.
- [ ] **Step 5: Commit** `Локальное хранилище: память, IndexedDB, SQLite`.

---

### Task 7: Очередь отправки в браузере

**Files:**
- Create: `src/core/sync/uploader.ts`, `src/core/sync/web-uploader.ts`
- Test: `src/core/sync/web-uploader.test.ts`

**Interfaces:**
- Consumes: Task 5 (`StorageBackend`, ошибки, `FakeBackend`), Task 6 (`OutboxStore`, `BlobStore`).
- Produces:

```ts
interface UploadStatus { pending: number; needsAuth: boolean; quotaFull: boolean; lastError?: string }
interface Uploader {
  enqueueBytes(key: string, data: Uint8Array, lane: 'entry' | 'attachment'): Promise<void>
  status(): Promise<UploadStatus>
  completed(): Promise<string[]>             // отправленные, но ещё не подтверждённые
  ack(names: string[]): Promise<void>        // вызывается после markPushed; только тогда элементы удаляются из очереди
  kick(): Promise<void>        // веб: отправить всё, что получится (один активный проход); Android: запланировать работу
}
class WebUploader implements Uploader {
  constructor(deps: { backend: StorageBackend; outbox: OutboxStore; blobs: BlobStore })
  enqueueBlob(key: string, blobKey: string, size: number): Promise<void>   // lane 'attachment'
}
```

Алгоритм `kick`. **Активный проход всегда один:** вызов во время прохода не запускает второй, а возвращает тот же промис и ставит отметку «пройти ещё раз» после текущего, чтобы не пропустить новые элементы. Между вкладками это гарантирует блокировка одной вкладки из Task 10. Сначала элементы `entry`, потом `attachment`. Для каждого: `backend.upload(key, source, size, item.backendState, s => outbox.updateOutbox(key, { backendState: s }))`, после успеха `state: 'done'`. Как именно плагин докачивает и узнаёт уже загруженное, очередь не знает (для Drive это описано в Task 5). При `IntegrityError` выставить `state: 'failed'` и `lastError`: так быть не должно, это сигнал ошибки в коде. При `AuthRequiredError` выставить `needsAuth` и остановиться. При `QuotaError` выставить `quotaFull` и остановиться. При `TransientError` увеличить `attempts`, сохранить `lastError` и остановиться (следующий `kick` повторит). Успех сбрасывает флаги.

- [ ] **Step 1: Написать падающие тесты** (`FakeBackend` + `MemoryStore`)

```ts
test('маленький элемент → объект с нужным ключом; completed отдаёт ключ до ack, после ack пусто', ...)
test('перекрывающиеся kick создают один объект', ...)
test('TransientError на upload → следующий kick создаёт ровно один объект', ...)
test('состояние плагина переживает перезапуск очереди', async () => {
  // FakeBackend chunkSize 1024, данные 5000 байт; failNext('upload') посреди загрузки;
  // новый WebUploader поверх того же хранилища → kick: upload получает сохранённый backendState, объект один, содержимое равно исходному
})
test('ошибка авторизации ставит очередь на паузу без потери смещения', async () => {
  // после AuthRequiredError: status().needsAuth === true, у элемента state 'pending' и backendState сохранён; после восстановления kick завершает
})
test('IntegrityError → элемент failed с lastError, остальные идут дальше', ...)
test('QuotaError → quotaFull, элемент остаётся pending', ...)
test('записи уходят раньше вложений', ...)
```

- [ ] **Step 2: Запустить** `npx vitest run src/core/sync/web-uploader.test.ts`. Ожидается FAIL.
- [ ] **Step 3: Реализовать** `WebUploader`.
- [ ] **Step 4: Запустить** тот же тест. Ожидается PASS.
- [ ] **Step 5: Commit** `Очередь отправки в браузере`.

---

### Task 8: Приём изменений из хранилища и движок синхронизации

**Files:**
- Create: `src/core/sync/puller.ts`, `src/core/sync/engine.ts`
- Test: `src/core/sync/two-devices.test.ts`

**Interfaces:**
- Consumes: Task 4 (`parseVersionKey`, `keyringKey`), Task 5, Task 6, Task 7.
- Produces:
  - `interface PullResult { newVersions: number; changedEntryIds: string[] }`
  - `pull(backend: StorageBackend, store: LocalStore, opts?: { concurrency?: number /* 6 */ }): Promise<PullResult>`
  - `interface Binding { storage: string /* kind плагина */; keyId: string }`
  - `checkBinding(backend: StorageBackend, b: Binding): Promise<boolean>`: `backend.kind === b.storage` и `stat(keyringKey(b.keyId))` не `null`
  - `interface SyncReport { needsAuth: boolean; offline: boolean; wrongAccount: boolean; pull: PullResult | null; upload: UploadStatus }`
  - `class SyncEngine { constructor(deps: { backend: StorageBackend; store: LocalStore; uploader: Uploader; binding: Binding }); syncNow(): Promise<SyncReport> }`

`pull`: `backend.changes(cursor)`, где `cursor` берётся из meta `storage.cursor` (`null` при первом запуске). Обработка каждого объекта порции: `putRemote`. Если `parseVersionKey(key)` дал версию и её ещё нет, то `download` и `putVersion({ ...meta, sealed, pushed: true })`. Если версия есть локально с `pushed: false`, вызвать `markPushed`: объект в хранилище доказывает, что отправка состоялась. Удалённые объекты на этом этапе игнорируются. **Новый курсор записывается в meta только после успешной обработки всей порции.** Если скачивание прервалось, курсор остаётся прежним, и следующий `pull` получит те же объекты снова. Это безопасно, потому что обработка идемпотентна.

`syncNow`: сначала `checkBinding`. Если подключено другое облако или другой аккаунт (объекта ключей нет), вернуть `wrongAccount: true` и ничего не отправлять и не принимать. Иначе `uploader.kick()`, затем для каждого ключа из `completed()`, который `parseVersionKey` признаёт версией, вызвать `markPushed(versionId)`, затем `ack(keys)`, затем `pull`.

**`syncNow` никогда не бросает ожидаемые ошибки, а возвращает их в отчёте.** `AuthRequiredError` на любом шаге (`checkBinding`, отправка, `pull`) даёт `needsAuth: true`. Это обычная ситуация: после перезагрузки страницы дневник на месте, а токен Google, который жил только в памяти, пропал. `TransientError` даёт `offline: true`. `QuotaError` приходит через `upload.quotaFull`. Неожиданные ошибки пробрасываются.

- [ ] **Step 1: Написать падающие тесты** (два устройства = два `MemoryStore` и два `WebUploader` над одним `FakeBackend` с заранее положенным объектом `kr/<keyId>`, версии собираются через `encodeVersion`)

```ts
test('версия с A появляется у B с pushed=true', ...)
test('повторный pull не создаёт дублей', async () => { /* второй pull: newVersions 0; полный повтор (сброс storage.cursor) — число версий то же */ })
test('первый pull с cursor null, следующие по сохранённому курсору', ...)
test('обрыв скачивания посреди pull → курсор не сдвинулся; следующий pull докачивает пропущенную версию', ...)
test('после отправки A помечает свою версию pushed', ...)
test('сбой между completed и markPushed → следующий syncNow помечает pushed и делает ack', ...)
test('pull помечает pushed свою версию, найденную в хранилище', ...)
test('другой аккаунт (нет kr/<keyId>) → wrongAccount, ничего не отправлено и не принято', ...)
test('другой вид хранилища в binding → wrongAccount', ...)
test('сохранённый дневник без токена: checkBinding получает AuthRequiredError → syncNow не бросает, needsAuth true, очередь цела', ...)
test('нет сети при checkBinding → offline true, syncNow не бросает', ...)
```

- [ ] **Step 2: Запустить** `npx vitest run src/core/sync/two-devices.test.ts`. Ожидается FAIL.
- [ ] **Step 3: Реализовать** `pull` и `SyncEngine`. Скачивание параллельное, не больше `concurrency` одновременно.
- [ ] **Step 4: Запустить** тот же тест. Ожидается PASS.
- [ ] **Step 5: Commit** `Приём изменений и движок синхронизации`.

---

### Task 9: Сервис дневника: черновики, версии, корзина, конфликты, вложения в браузере

**Files:**
- Create: `src/core/diary.ts`, `src/core/attachments.ts`
- Test: `src/core/diary.test.ts`, `src/core/attachments.test.ts`

**Interfaces:**
- Consumes: Task 2 (`seal`, `open`, `encryptStream`, `decryptAll`), Task 4, Task 6, Task 7, Task 8 (в тестах).
- Produces:

```ts
interface EntrySummary { entryId: string; date: string; tz: string; title: string; preview: string /* первые 140 символов текста */; tagIds: string[]; mood: number | null; hasAttachments: boolean; conflict: boolean; damaged: boolean; unsynced: boolean }
interface ConflictSide { versionId: string; state: VersionState; savedAt: number; deviceId: string; content: EntryContent }
interface EntryView { entryId: string; content: EntryContent; base: string | null /* версия, на которой основано показанное содержимое */; fromDraft: boolean; conflict: ConflictSide[] | null }
class ConflictError extends Error {}
class Diary {
  constructor(deps: { store: LocalStore; uploader: Uploader; key: DiaryKey; deviceId: string; now?: () => number; tz?: string })
  createEntry(): Promise<string>
  saveDraft(entryId: string, content: EntryContent, base: string | null): Promise<void>   // base передаёт редактор, Diary его не подставляет
  seal(entryId: string): Promise<string | null>   // версия, от которой продолжать правку: новая или прежняя base, если менять было нечего; null, если черновика нет
  sealAll(): Promise<void>
  recover(): Promise<void>                                   // при старте: все версии с pushed=false снова в очередь (идемпотентно по имени)
  trash(entryId: string): Promise<void>                      // при конфликте бросает ConflictError
  list(): Promise<EntrySummary[]>                           // без trashed, по date убыв.
  get(entryId: string): Promise<EntryView>
  resolveConflict(entryId: string, keepVersionId: string): Promise<void>
}
interface AttachmentStore { add(entryId: string, files: Blob[] | 'native-picker'): Promise<AttachmentRef[]>; readPlain(ref: AttachmentRef): Promise<Blob> }
class WebAttachmentStore implements AttachmentStore { constructor(deps: { blobs: BlobStore; uploader: WebUploader; key: DiaryKey; backend: StorageBackend; store: LocalStore }) }
```

Правила:
- **Очерёдность.** Все операции над одной записью (`saveDraft`, `seal`, `trash`, `resolveConflict`) выполняются строго по очереди: у каждой записи внутри `Diary` своя цепочка промисов. Даже `seal`, вызванный сразу после `saveDraft` без `await`, запечатает последний текст.
- **Черновик:** содержимое запечатано с контекстом `draft:<entryId>`. Рядом открыто лежат номер редакции `rev` (каждый `saveDraft` его увеличивает) и `base`: версия, от которой начата правка. **`base` задаёт вызывающий**: это версия, которую показывает редактор (`EntryView.base` при открытии, потом результат `seal`). Diary не подставляет текущую голову сам. Иначе версия, пришедшая с другого устройства, пока редактор открыт, стала бы родителем текста, написанного поверх старой версии, и чужая правка пропала бы без конфликта. С переданной базой получаются две ветки и честный конфликт. Запись, у которой уже есть конфликт, в редакторе не открывается, пока конфликт не разрешён. Это локальное автосохранение, в хранилище оно не уходит.
- **seal:** прочитать черновик вместе с `rev` и `base`. Если содержимое совпадает с версией `base`, удалить черновик через `deleteDraftIfRev`. Иначе создать новую версию (`parents = base ? [base] : []`, `state: 'live'`, `versionId = newId()`, в `VersionPayload` текущие `savedAt` и `deviceId`), выполнить `encodeVersion`, затем **одной транзакцией** `commitSeal(version, rev)`: версия сохраняется, а черновик либо удаляется, либо (если его успели изменить) переводится на `base` = новая версия. Только после этого `uploader.enqueueBytes(versionKey(meta), sealed, 'entry')`. **Ошибка постановки в очередь из `seal` не пробрасывается:** версия уже сохранена локально, поэтому `seal` возвращает её id, и редактор продолжает правку от неё. Ошибка записывается в лог, а версию снова поставит в очередь `recover()`, который вызывается перед каждой синхронизацией. Сам по себе `seal` никогда не сливает конфликт.
- **Восстановление после сбоя.** Состояние «версия сохранена, а черновик ещё указывает на старую базу» невозможно: это одна транзакция. Если процесс упал между `commitSeal` и постановкой в очередь, версия лежит с `pushed: false` без задания на отправку. `recover()` при каждом запуске заново ставит все такие версии в очередь. Это безопасно: очередь не принимает ключ, который в ней уже есть в любом состоянии (до `ack`), а уже отправленную версию `pull` помечает `pushed` по объекту в хранилище.
- **trash:** новая версия с `state: 'trashed'`, `parents = [голова]` и тем же содержимым, что у головы, чтобы удаление можно было отменить.
- **resolveConflict:** новая версия с содержимым **и состоянием** (`live` или `trashed`) выбранной головы, `parents` = все головы. Если выбрана удалённая сторона, запись остаётся в корзине. Стороны конфликта в `EntryView` отсортированы по `savedAt` после расшифровки, новые первыми.
- **list и get:** если версию не удалось расшифровать, запись получает `damaged: true`, но остальные записи показываются. `unsynced` выставляется, если есть черновик или версия с `pushed: false`.
- **Вложения в браузере:** `add` для каждого файла: `id = newId()`, `encryptStream` с контекстом `att:<id>` в `BlobStore` под ключом `att:<id>`, затем `uploader.enqueueBlob(attachmentKey(id), 'att:' + id, encryptedSize)`. `kind` берётся из MIME. `readPlain`: локальный blob, иначе `store.remoteByKey(attachmentKey(id))` (а если его нет, `backend.stat`), `backend.download`, `putBlob` и `decryptAll`. `'native-picker'` в браузере бросает ошибку.

- [ ] **Step 1: Написать падающие тесты**

```ts
test('createEntry → get: пустое содержимое с текущей датой и поясом, fromDraft true', ...)
test('черновик переживает новый экземпляр Diary', ...)          // Review Focus 1
test('seal: в очереди ключ versionKey(новой версии), черновик удалён; повторный seal без правок не создаёт версию', ...)
test('seal сразу после saveDraft без await запечатывает последний текст', ...)
test('seal не удаляет более новый черновик', async () => {
  // поддельный uploader.enqueueBytes во время seal пишет в store новый черновик (rev+1);
  // после seal черновик на месте, с новым текстом и base = только что созданная версия
})
test('сбой между commitSeal и очередью → recover ставит версию в очередь; повторный recover не дублирует', ...)
test('версия с другого устройства пришла между открытием записи и первым автосохранением → после seal конфликт из двух веток, текст обеих на месте', async () => {
  // A: get(e) → base = V1; B правит и отправляет V2; A: syncNow (V2 получена), затем saveDraft(e, текст_A, V1) и seal;
  // resolve(versionsOf(e)) === conflict с головами V2 и V3, у V3 parents = [V1]
})
test('ошибка очереди после commitSeal: seal не бросает и возвращает новую версию; следующая правка в той же сессии даёт её потомка; recover ставит её в очередь', ...)
test('после сбоя и recover следующая правка и seal дают потомка, а не вторую ветку', async () => {
  // uploader.enqueueBytes падает один раз во время seal; новый Diary над тем же store → recover → saveDraft → seal;
  // resolve(versionsOf(e)) === single, у новой версии parents = [версия до сбоя]
})
test('правка после seal → новая версия с parents [предыдущая]', ...)
test('одновременная правка на двух устройствах → conflict, resolveConflict оставляет выбранную, parents = обе головы', ...)
test('trash → запись пропала из списка и на втором устройстве после синхронизации', ...)
test('удаление против правки: у сторон конфликта есть state; выбор удалённой → запись в корзине, выбор живой → запись в списке', ...)
test('повреждённая версия помечена, остальные в списке', ...)   // Review Focus 5
test('вложение: add ставит в очередь ao/<id>; на втором устройстве readPlain возвращает исходные байты', ...)
```

- [ ] **Step 2: Запустить** `npx vitest run src/core/diary.test.ts src/core/attachments.test.ts`. Ожидается FAIL.
- [ ] **Step 3: Реализовать** `Diary` и `WebAttachmentStore`.
- [ ] **Step 4: Запустить** `npx vitest run`. Ожидается PASS (весь набор).
- [ ] **Step 5: Commit** `Сервис дневника и вложения в браузере`.

---

### Task 10: Веб: вход в Google, запуск дневника, минимальный интерфейс

**Files:**
- Create: `src/platform/types.ts`, `src/platform/web/gis-auth.ts`, `src/platform/web/index.ts`, `src/app/bootstrap.ts`
- Create: `src/ui/strings.ts`, `src/ui/App.tsx`, `src/ui/SyncBar.tsx`, `src/ui/screens/Connect.tsx`, `src/ui/screens/CreateDiary.tsx`, `src/ui/screens/Unlock.tsx`, `src/ui/screens/EntryList.tsx`, `src/ui/screens/EntryEditor.tsx`, `src/ui/screens/Conflict.tsx`, `src/ui/index.css`, `src/ui/editor-session.ts`
- Test: `src/app/bootstrap.test.ts`, `src/ui/editor-session.test.ts`

**Interfaces:**
- Consumes: Tasks 3, 5–9.
- Produces:

```ts
interface Platform {
  kind: 'web' | 'android'; storage: StoragePlugin /* в этом этапе всегда gdrive (или fake) */; store: LocalStore; uploader: Uploader
  attachments(key: DiaryKey): AttachmentStore
  onKeyUnlocked(key: DiaryKey): Promise<void>      // Android: передать ключ в натив (Task 13); веб: ничего
  setBinding(b: Binding): Promise<void>            // Android: передать в Sync-плагин, чтобы фоновая отправка тоже проверяла аккаунт; веб: ничего
}
type BootState =
  | { kind: 'connect' } | { kind: 'create' } | { kind: 'resume-create' } | { kind: 'show-recovery'; recoveryKey: string }
  | { kind: 'unlock'; keyring: KeyringFile } | { kind: 'multiple-diaries' }
  | { kind: 'ready'; diary: Diary; engine: SyncEngine; attachments: AttachmentStore }
class Bootstrap {
  constructor(p: Platform)
  start(): Promise<BootState>
  afterConnect(): Promise<BootState>
  create(password: string): Promise<BootState>                 // → show-recovery | multiple-diaries
  resumeCreate(password: string): Promise<BootState>           // продолжить прерванное создание
  confirmRecoverySaved(): Promise<BootState>                   // → ready
  unlock(secret: { password: string } | { recoveryKey: string }): Promise<BootState>
}
class EditorSession { constructor(diary: Diary, entryId: string, base: string | null /* EntryView.base */, debounceMs?: number /* 500 */); change(c: EntryContent): void; flush(): Promise<void>; checkpoint(): Promise<void> /* flush + seal, сессия остаётся открытой */; close(): Promise<void> }
function createWebPlatform(opts: { fakeStorage: boolean }): Promise<Platform>
```

- Объект ключей в хранилище: ключ `kr/<keyId>` (`keyringKey`), тело JSON `KeyringFile`. Локальная копия в meta `keyring`, идентификатор устройства в meta `deviceId` (создаётся один раз через `newId()`). Привязка к хранилищу хранится в meta `binding` (`Binding` из Task 8: вид плагина и `keyId`). Она выставляется после создания дневника или первого открытия из хранилища и передаётся в `platform.setBinding`. Вид хранилища для нового дневника: `gdrive` (выбор появится вместе со вторым плагином).
- `start`: если в meta есть `pendingCreate`, состояние `resume-create`. Если есть локальный keyring, состояние `unlock`. Иначе, если `storage.auth.isConnected()`, то `afterConnect()`, иначе `connect`.
- **Переподключение на настроенном устройстве.** Если в meta уже есть `binding`, `afterConnect` ничего не заменяет и не создаёт: он только вызывает `checkBinding` с сохранённой привязкой. Если проверка прошла, состояние прежнее (`unlock` или `ready`) и синхронизация продолжается. Если нет (подключён аккаунт с пустым хранилищем или с другим дневником), локальные `keyring`, `binding`, записи и очередь остаются как были, строка синхронизации показывает предупреждение о другом аккаунте, а в чужом хранилище не создаётся ни объекта ключей, ни чего-либо ещё. Привязку к другому хранилищу в первой версии сменить нельзя.
- `afterConnect` на ненастроенном устройстве (`binding` нет): `backend.list('kr/')` и разбор `parseKeyringKey`. Если среди них **разные** `keyId`, состояние `multiple-diaries`: выбирать первый попавшийся нельзя. Если `keyId` один (объектов с ним может быть несколько, это дубли одной отправки), скачать любой, сохранить в meta `keyring` и `binding`, состояние `unlock`. Если объектов нет: `create`.
- `create(password)` требует сети и устойчив к сбою: `createKeyring`, затем **до загрузки** сохранить в meta `pendingCreate = { file, uploadState: {}, recoverySealed }`, где `recoverySealed = seal(key, 'recovery-display', utf8(recoveryKey))`. Потом `backend.upload(keyringKey(keyId), …, pendingCreate.uploadState, s => сохранить в pendingCreate)`: повтор с сохранённым состоянием безопасен. Затем снова `backend.list('kr/')`. Если появился объект ключей с другим `keyId` (второе устройство создавало дневник одновременно), состояние `multiple-diaries`. Иначе сохранить `keyring` и `binding`, состояние `show-recovery`. `confirmRecoverySaved()` удаляет `pendingCreate` и переводит в `ready`. При `resume-create` пользователь вводит тот же пароль, `resumeCreate` открывает файл из `pendingCreate`, продолжает загрузку с сохранённым состоянием и снова показывает тот же ключ восстановления. **[решение исполнителя]** Первая настройка без входа в Google невозможна, иначе можно получить два разных дневника.
- **Одна вкладка.** `main.tsx` берёт `navigator.locks.request('mj-app', { ifAvailable: true }, …)` на всё время жизни страницы. Если блокировка занята, показывается только экран «Дневник уже открыт в другой вкладке.» Так очередь отправки и черновики никогда не обрабатываются двумя вкладками сразу.
- Плагин `gdrive` в вебе: `createStorage('gdrive', { auth: new GisAuth(...) })`. Вход через GIS `google.accounts.oauth2.initTokenClient({ client_id: import.meta.env.VITE_GOOGLE_WEB_CLIENT_ID, scope: 'https://www.googleapis.com/auth/drive.appdata' })`. Токен хранится только в памяти, до истечения `expires_in`. Скрипт `https://accounts.google.com/gsi/client` подгружается динамически.
- `VITE_FAKE_STORAGE=1` подключает `FakeBackend` и вход-заглушку. Это нужно, чтобы проверять интерфейс до Task 14.
- При старте веб-платформа вызывает `navigator.storage.persist()`, чтобы браузер не вытеснил неотправленные правки (раздел 6.8 проектного документа).
- Цикл синхронизации в вебе: **перед каждым** `engine.syncNow()` вызывается `diary.recover()` (это дёшево и идемпотентно). Синхронизация запускается при переходе в `ready`, раз в 60 секунд, по событию `online` и после `seal`. При `wrongAccount` строка синхронизации показывает предупреждение, отправка и приём стоят, пока не подключён нужный аккаунт. При `needsAuth` показывается «Нужно переподключить Google» с кнопкой «Переподключить»: её обработчик вызывает `storage.auth.connect()`, затем `afterConnect()` (на настроенном устройстве это только проверка привязки) и `syncNow()`. При `offline` синхронизация молча повторяется по таймеру и по событию `online`.
- Редактор: Tiptap StarterKit и поле заголовка. Сохраняет только через `EditorSession`: `change` откладывает `saveDraft` на 500 мс; `flush` отменяет таймер и сразу сохраняет последнее содержимое; `checkpoint` выполняет `flush`, потом `seal`, и сессия продолжает работать: следующая правка начнёт новый черновик от только что созданной версии. `close` делает то же самое и после этого игнорирует `change`. `visibilitychange: hidden`, пауза приложения на Android и таймер 60 секунд вызывают `checkpoint`. **Только явный выход из редактора вызывает `close`**: пауза бывает и тогда, когда пользователь просто открыл системный выбор фото. **База правки:** сессия хранит `base` с момента открытия записи и передаёт её в каждый `saveDraft`. После `checkpoint` или `close` база заменяется результатом `seal`, **если он не `null`**: `null` значит, что черновика не было, и база остаётся прежней. Иначе открытая без правок запись после срабатывания таймера потеряла бы базу, и следующая версия вышла бы без родителя. Собственные операции сессии (`saveDraft` по таймеру, `flush`, `checkpoint`) идут по своей цепочке, а `base` читается в момент выполнения. Поэтому правка, сделанная во время `checkpoint`, сохраняется уже от новой версии, без ложной развилки. Так быстрый выход сразу после правки не теряет её и не оставляет отложенного сохранения после запечатывания.
- Тексты (`strings.ts`, дословно):
  - Подключение: «Подключить Google Drive». Пояснение: «Дневник хранится в скрытой папке приложения на вашем Google Drive в зашифрованном виде.»
  - Создание: «Придумайте пароль дневника», «Повторите пароль», «Пароль должен быть не короче 8 символов», «Пароли не совпадают».
  - Ключ восстановления: «Ключ восстановления», «Запишите или распечатайте его. Если забудете пароль, записи можно будет открыть только этим ключом.», «Я сохранил ключ».
  - Вход: «Пароль дневника», «Открыть», «Неверный пароль», «Войти по ключу восстановления», «Неверный ключ восстановления».
  - Список: «Новая запись», отметки «Конфликт», «Повреждена», «Не отправлено».
  - Редактор: «Заголовок», «Фото или видео».
  - Строка синхронизации: «Синхронизировано», «Отправляется: {n}», «Нужно переподключить Google», «Переподключить», «Нет места на Google Drive», «Подключён другой Google-аккаунт. На нём нет этого дневника, поэтому синхронизация остановлена. Переподключите аккаунт, в котором хранится дневник.»
  - Прерванное создание: «Создание дневника не завершилось. Введите пароль, чтобы продолжить.»
  - Несколько дневников: «На этом Google Drive найдено несколько разных дневников. Чтобы ничего не перепутать, работа остановлена.»
  - Вторая вкладка: «Дневник уже открыт в другой вкладке.»
  - Конфликт: «Эту запись изменили на двух устройствах. Выберите версию, которую оставить.», «Оставить эту».
- Тема: светлая и тёмная по `prefers-color-scheme`, через CSS-переменные.

- [ ] **Step 1: Написать падающие тесты** `bootstrap.test.ts` (`FakeBackend`, `MemoryStore`, вход-заглушка, `iterations` подменяются через `vi.mock` на 1000)

```ts
test('чистое устройство без входа → connect', ...)
test('afterConnect на пустом хранилище → create; create → show-recovery (13 групп), в хранилище один kr/<keyId>; confirmRecoverySaved → ready', ...)
test('сбой после записи pendingCreate → start даёт resume-create; resumeCreate тем же паролем: один объект ключей, тот же ключ восстановления', ...)
test('ответ на загрузку ключей потерян (loseResponse) → повтор не создаёт второй объект', ...)
test('в хранилище два объекта ключей с разными keyId → multiple-diaries', ...)
test('второе устройство: afterConnect → unlock; верный пароль → ready, сохранена binding, вызван setBinding', ...)
test('неверный пароль не меняет состояние', async () => { /* бросает WrongSecretError; meta keyring тот же; повторный start → unlock */ })
test('вход по ключу восстановления → ready', ...)
test('переподключение к аккаунту с пустым хранилищем: binding и keyring прежние, там ничего не создано, синхронизация сообщает wrongAccount', ...)
test('переподключение к аккаунту с другим дневником: binding и keyring прежние, wrongAccount', ...)
test('запуск с сохранённым дневником без токена → unlock → ready; syncNow даёт needsAuth, а не исключение', ...)
// editor-session.test.ts (MemoryStore + поддельный uploader, таймеры vi.useFakeTimers)
test('change и сразу close → версия с последним текстом', ...)
test('после close отложенный saveDraft не выполняется', ...)
test('checkpoint (пауза на время выбора фото) → правка после возврата сохраняется, следующий checkpoint даёт версию-потомка', ...)
test('правка во время checkpoint сохраняется от новой версии: после следующего checkpoint resolve === single', ...)
test('saveDraft получает base, зафиксированную при открытии, даже если голова записи с тех пор сменилась', ...)
test('checkpoint без правок не меняет base: открыть V1, таймер, потом правка и checkpoint → новая версия с parents [V1]', ...)
```

- [ ] **Step 2: Запустить** `npx vitest run src/app src/ui`. Ожидается FAIL.
- [ ] **Step 3: Реализовать** `Bootstrap`, веб-платформу и GIS-вход.
- [ ] **Step 4: Запустить** `npx vitest run`. Ожидается PASS.
- [ ] **Step 5: Реализовать экраны** по текстам выше.
- [ ] **Step 6: Проверить вручную с поддельным хранилищем:** `VITE_FAKE_STORAGE=1 npm run build && npm run preview`, затем открыть `http://localhost:4173` в браузере. Ожидается: создание дневника, показ ключа, новая запись, текст и фото сохраняются, после перезагрузки страницы и ввода пароля запись на месте, строка синхронизации показывает «Синхронизировано».
- [ ] **Step 7: Commit** `Веб: вход в Google, запуск дневника, минимальный интерфейс`.

---

### Task 11: Android-проект, сборка в Docker, потоковое шифрование на Kotlin

**Files:**
- Create: `capacitor.config.ts`, `android/` (через `npx cap add android`), `docker/gradle.sh`
- Modify: `android/variables.gradle` (`minSdkVersion = 30`), `android/build.gradle` (Kotlin Gradle plugin), `android/app/build.gradle` (применение Kotlin, зависимости, тестовый `systemProperty`)
- Create: `android/app/src/main/java/io/github/bol970/myjourney/crypto/StreamCipher.kt`
- Test: `android/app/src/test/java/io/github/bol970/myjourney/crypto/StreamCipherVectorsTest.kt`

**Interfaces:**
- Consumes: формат потока и `testdata/vectors/stream-v1.json` из Task 2.
- Produces:

```kotlin
object StreamCipher {
  const val CHUNK = 1 shl 20
  fun encrypt(dek: ByteArray, keyId: ByteArray, context: String, input: InputStream, output: OutputStream, chunkSize: Int = CHUNK, salt: ByteArray = randomBytes(16), noncePrefix: ByteArray = randomBytes(7)): Long   // возвращает размер открытых данных
  fun decrypt(dek: ByteArray, keyId: ByteArray, context: String, input: InputStream, output: OutputStream)
  fun encryptedSize(plainSize: Long, chunkSize: Int = CHUNK): Long
}
class DecryptException(message: String) : Exception(message)
```

- [ ] **Step 1: Подключить Capacitor:** установить `@capacitor/core`, `@capacitor/cli`, `@capacitor/android`, `@capacitor/app` (последние стабильные), выполнить `npx cap init "Мой дневник" io.github.bol970.myjourney --web-dir dist` и `npx cap add android`. Поставить `minSdkVersion = 30`. **Подключить Kotlin:** шаблон Capacitor создаёт Java-проект без Kotlin. Добавить Kotlin Gradle plugin (`org.jetbrains.kotlin.android`, версия, совместимая с AGP шаблона) в `android/build.gradle`, применить его в `android/app/build.gradle`, выставить `kotlinOptions.jvmTarget` как у Java. `MainActivity.java` остаётся на Java и регистрирует Kotlin-плагины через `registerPlugin(...)` до `super.onCreate`.
- [ ] **Step 2: Написать** `docker/gradle.sh`. Образ берётся из переменной `MJ_ANDROID_IMAGE`, по умолчанию свежий тег `cimg/android:<YYYY.MM>-node` с Docker Hub с SDK под `compileSdk` текущего Capacitor. Выбранный тег записать в скрипт. Скрипт запускает `docker run --rm --user "$(id -u):$(id -g)" -e GRADLE_USER_HOME=/gradle -v mj-gradle:/gradle -v "$PWD":/work -w /work/android "$IMAGE" ./gradlew "$@"`. Однократная подготовка тома: `docker run --rm -v mj-gradle:/gradle alpine chown "$(id -u):$(id -g)" /gradle`.
- [ ] **Step 3: Проверить сборку:** `npm run build && npx cap sync android && docker/gradle.sh assembleDebug`. Ожидается `BUILD SUCCESSFUL`.
- [ ] **Step 4: Написать падающий тест** `StreamCipherVectorsTest`: читает JSON по пути из `System.getProperty("mj.vectors")` (в `build.gradle`: `testOptions.unitTests.all { systemProperty "mj.vectors", rootProject.file("../testdata/vectors/stream-v1.json").absolutePath }`, разбор через `testImplementation "org.json:json:<последняя>"`). Для каждого случая шифрование с фиксированными `salt` и `noncePrefix` даёт `cipherHex` или `cipherSha256`, расшифровка возвращает открытый текст, поток без последнего блока даёт `DecryptException`.
- [ ] **Step 5: Запустить** `docker/gradle.sh :app:testDebugUnitTest`. Ожидается FAIL.
- [ ] **Step 6: Реализовать** `StreamCipher` на `javax.crypto` (`AES/GCM/NoPadding`, `GCMParameterSpec(128, nonce)`, `updateAAD`; HKDF-SHA-256 через `Mac.getInstance("HmacSHA256")`, extract + expand на 32 байта). Чтобы знать, какой блок последний, читать на один блок вперёд.
- [ ] **Step 7: Запустить** `docker/gradle.sh :app:testDebugUnitTest`. Ожидается PASS. **Проверить, что тест действительно выполнялся**, а не пропущен как `NO-SOURCE`: в `android/app/build/test-results/testDebugUnitTest/TEST-io.github.bol970.myjourney.crypto.StreamCipherVectorsTest.xml` атрибут `tests` больше 0 и `failures="0"`.
- [ ] **Step 8: Commit** `Android-проект, сборка в Docker, шифрование на Kotlin`.

---

### Task 12: Android: очередь, фоновая загрузка и Kotlin-часть плагина Google Drive

**Files:**
- Create (в `android/app/src/main/java/io/github/bol970/myjourney/`): `storage/StorageBackend.kt`, `storage/Storages.kt`, `storage/gdrive/DriveAuth.kt`, `storage/gdrive/AuthPlugin.kt`, `storage/gdrive/GoogleDriveBackend.kt`, `sync/OutboxDb.kt`, `sync/UploadRunner.kt`, `sync/UploadWorker.kt`, `sync/UploadScheduler.kt`, `sync/SyncPlugin.kt`
- Modify: `MainActivity.java` (регистрация плагинов), `android/app/build.gradle` (`androidx.work:work-runtime-ktx`, `com.google.android.gms:play-services-auth`, `org.jetbrains.kotlinx:kotlinx-coroutines-play-services`, `com.squareup.okhttp3:okhttp`, `testImplementation com.squareup.okhttp3:mockwebserver`)
- Test: `android/app/src/test/java/io/github/bol970/myjourney/storage/gdrive/GoogleDriveBackendTest.kt`, `android/app/src/test/java/io/github/bol970/myjourney/sync/UploadRunnerTest.kt`

**Interfaces:**
- Produces (Kotlin):

```kotlin
// Kotlin-часть любого плагина хранилища: только то, что нужно фоновой отправке
interface StorageBackend {
  val kind: String
  suspend fun upload(key: String, file: File, size: Long, state: JSONObject, persist: (JSONObject) -> Unit)   // идемпотентно по key, как в TS (Task 5)
  suspend fun exists(key: String): Boolean
}
object Storages { fun create(kind: String, context: Context): StorageBackend }   // реестр; в этом этапе только "gdrive", неизвестный kind → IllegalArgumentException
class AuthException : Exception(); class QuotaException : Exception(); class TransientException(cause: Throwable?) : Exception(cause); class IntegrityException : Exception()
object DriveAuth {
  const val SCOPE = "https://www.googleapis.com/auth/drive.appdata"
  suspend fun tokenOrNull(context: Context): String?          // без UI: null, если нужно согласие
}
class GoogleDriveBackend(private val http: OkHttpClient, private val token: suspend () -> String? /* DriveAuth.tokenOrNull; null → AuthException */, private val base: HttpUrl = "https://www.googleapis.com/".toHttpUrl(), private val chunkSize: Int = 8 shl 20) : StorageBackend
data class OutboxRow(val key: String, val path: String, val size: Long, val lane: String /* entry|attachment */, var backendState: String /* JSON */, var attempts: Int, var state: String /* pending|done|failed */, var lastError: String?, val enqueuedAt: Long)
interface OutboxRepo { fun enqueue(row: OutboxRow): Boolean /* false, если ключ уже есть в любом состоянии */; fun pending(lane: String): List<OutboxRow>; fun update(row: OutboxRow); fun done(): List<String>; fun delete(keys: List<String>); fun pendingCount(): Int }
class OutboxDb(context: Context) : OutboxRepo                    // SQLiteOpenHelper
interface SyncFlags { var needsAuth: Boolean; var quotaFull: Boolean; var wrongAccount: Boolean; var lastError: String? }   // SharedPreferences "sync"; в тестах — в памяти
sealed interface RunResult { object Success : RunResult; object Retry : RunResult }
// Вся логика воркера без зависимостей от WorkManager, чтобы её можно было проверить обычным JVM-тестом
class UploadRunner(private val repo: OutboxRepo, private val backend: StorageBackend?, private val binding: Pair<String, String>? /* storage, keyId */, private val flags: SyncFlags, private val fileOf: (OutboxRow) -> File) {
  suspend fun run(lane: String, isStopped: () -> Boolean): RunResult
}
object UploadScheduler { fun schedule(context: Context, lane: String, replace: Boolean = false) }   // читает настройку allowMetered из SharedPreferences "sync"
```

- Плагин `Auth` (JS-имя `Auth`): `authorize({ interactive: boolean }) → { accessToken }`. При `interactive: false`, когда нужно согласие, отклоняется с кодом `NEEDS_UI`. Работает через `Identity.getAuthorizationClient(...).authorize(AuthorizationRequest)`. Если `hasResolution()` и `interactive`, запускается `PendingIntent` через `ActivityResultLauncher`.
- Плагин `Sync` (JS-имя `Sync`): `enqueueBytes({ key, data /* base64url */, lane })` пишет файл `filesDir/outbox/<sha256(key) в hex>.bin` (ключ содержит `/`, поэтому имя файла выводится из него), ставит строку в `OutboxDb` с `backendState = "{}"` и вызывает `UploadScheduler.schedule`. Ещё методы: `status() → { pending, needsAuth, quotaFull, wrongAccount, lastError }` (флаги лежат в SharedPreferences `sync`), `completed() → { keys }` (`OutboxDb.done()`), `ack({ keys })` (`OutboxDb.delete`, вызывается после `markPushed`), `kick()` (планирует обе очереди), `setBinding({ storage, keyId })` (в SharedPreferences `sync`), `setAllowMetered({ value })`.
- `UploadScheduler`: `OneTimeWorkRequest<UploadWorker>` с параметром `lane`. Ограничение сети: `CONNECTED` для `entry`, `UNMETERED` для `attachment` (или `CONNECTED`, если `allowMetered`). Экспоненциальная задержка от 30 секунд. Обычная постановка: `enqueueUniqueWork("upload-$lane", ExistingWorkPolicy.APPEND_OR_REPLACE)`. **`setAllowMetered` перепланирует очередь `attachment` с `ExistingWorkPolicy.REPLACE`:** иначе новая работа встанет в хвост цепочки за работой, которая ждёт Wi-Fi, и мобильная сеть не поможет. Прогресс при замене не теряется: он в `OutboxDb`, а воркер между частями проверяет `isStopped`.
- `UploadWorker` (`CoroutineWorker`) только собирает зависимости (`OutboxDb`, `Storages.create(binding.storage)`, привязку и флаги из SharedPreferences) и переводит результат `UploadRunner.run` в `Result.success()` или `Result.retry()`.
- `UploadRunner.run(lane)`:
  1. Если привязки нет или `backend.exists("kr/<keyId>")` вернул `false`: `wrongAccount = true`, `Success` без отправки (повторять бессмысленно, пока пользователь не подключит нужный аккаунт и приложение не вызовет `kick`).
  2. Для каждой строки `pending(lane)` по порядку: `backend.upload(row.key, fileOf(row), row.size, JSONObject(row.backendState)) { s -> row.backendState = s.toString(); repo.update(row) }`.
  3. **После успеха сначала** `row.state = "done"` и `repo.update(row)`, **и только потом** удалить файл `.bin`, если это строка `entry`. Зашифрованные оригиналы вложений остаются: это хранилище дневника. Если процесс упадёт между этими шагами, строка уже `done`: `completed()` её отдаст, а лишний файл безвреден.
  4. Если у строки `pending` нет файла (так быть не должно), строка получает `failed` с `lastError`, остальные идут дальше.
  5. Ошибки: `TransientException` даёт `Retry`. `QuotaException`: `quotaFull = true`, `Success`. `AuthException`: `needsAuth = true`, `Retry`. `IntegrityException`: строка `failed` с `lastError`, остальные идут дальше. Между строками проверяется `isStopped()`, при остановке `Retry`. Успешная отправка сбрасывает `needsAuth` и `wrongAccount`.
- `GoogleDriveBackend` повторяет протокол TS-плагина из Task 5 (имя файла = ключ, состояние `{ fileId, session, offset }`): `generateIds` с сохранением id до создания файла, multipart для файлов не больше 5 МиБ (409 → GET), возобновляемая загрузка частями `chunkSize` (кратно 256 КиБ). На 409 при старте сессии выполняется GET файла и сверка размера. Если сессия уже есть, сначала запрос состояния `Content-Range: bytes */N`. Ответ 200/201 с файлом означает, что всё уже загружено (ответ на последнюю часть потерялся). 404/410 означает, что сессия истекла: GET файла, и если он есть с нужным размером, готово, иначе новая сессия с 0. `exists(key)`: поиск в `appDataFolder` по имени. Токен берётся через `DriveAuth.tokenOrNull`, его отсутствие даёт `AuthException`. Ошибки: 401 → `AuthException`, 403 `storageQuotaExceeded` → `QuotaException`, 429, 5xx и `IOException` → `TransientException`, другой размер у существующего файла → `IntegrityException`.

- [ ] **Step 1: Написать падающие тесты** `GoogleDriveBackendTest` (`MockWebServer`, `base` = адрес сервера, токен-заглушка)

```kotlin
@Test fun `маленький файл - generateIds со space=appDataFolder, затем multipart с этим id и name = key`()
@Test fun `409 при создании - GET существующего и успех`()
@Test fun `GoogleDriveBackend продолжает сессию со смещения сервера`()   // state с session и offset=0; сервер на запрос состояния отвечает 308 Range bytes=0-262143; следующий PUT начинается с bytes 262144-
@Test fun `истёкшая сессия 404 - файла нет - новая сессия с нуля`()
@Test fun `истёкшая сессия 404 - файл уже есть с нужным размером - done без загрузки`()
@Test fun `запрос состояния вернул 200 с файлом - done без загрузки`()
@Test fun `409 при старте сессии - GET файла - done`()
@Test fun `exists - поиск по имени, пустой ответ даёт false`()
@Test fun `нет токена или 401 - AuthException, 403 storageQuotaExceeded - QuotaException, 503 - TransientException, другой размер - IntegrityException`()
// UploadRunnerTest: OutboxRepo и SyncFlags в памяти, поддельный StorageBackend, временная папка
@Test fun `успех - строка done записана раньше, чем удалён bin; completed отдаёт ключ`()   // журнал событий фиксирует порядок update(done) → delete(file)
@Test fun `падение после update(done) до удаления файла - следующий run не загружает повторно, completed отдаёт ключ`()
@Test fun `вложение - после успеха файл не удаляется`()
@Test fun `нет привязки или exists=false - wrongAccount, upload не вызывался, Success`()
@Test fun `TransientException - Retry, backendState сохранён; следующий run продолжает с ним`()
@Test fun `AuthException - needsAuth и Retry; QuotaException - quotaFull и Success`()
@Test fun `IntegrityException или пропавший файл - строка failed, следующие строки отправлены`()
```

- [ ] **Step 2: Запустить** `docker/gradle.sh :app:testDebugUnitTest`. Ожидается FAIL.
- [ ] **Step 3: Реализовать** `StorageBackend`, `Storages`, `GoogleDriveBackend`, `UploadRunner`, затем `OutboxDb` (`SQLiteOpenHelper`, база `outbox.db`, таблица с полями `OutboxRow`, `key` как PRIMARY KEY), `DriveAuth`, `AuthPlugin`, `UploadWorker`, `UploadScheduler`, `SyncPlugin`. Плагины зарегистрировать в `MainActivity`.
- [ ] **Step 4: Запустить** `docker/gradle.sh :app:testDebugUnitTest assembleDebug`. Ожидается PASS и `BUILD SUCCESSFUL`, тесты `GoogleDriveBackendTest` и `UploadRunnerTest` в отчёте выполнены (не `NO-SOURCE`).
- [ ] **Step 5: Commit** `Android: фоновая загрузка и плагин Google Drive на Kotlin`.

---

### Task 13: Android: ключ в нативе, вложения, связка с TypeScript

**Files:**
- Create (Kotlin): `key/KeySession.kt`, `key/KeySessionPlugin.kt`, `attachments/AttachmentRepo.kt`, `attachments/AttachmentsPlugin.kt`
- Create (TS): `src/platform/android/plugins.ts`, `src/platform/android/sqlite-executor.ts`, `src/platform/android/uploader.ts`, `src/platform/android/auth.ts`, `src/platform/android/attachments.ts`, `src/platform/android/index.ts`
- Modify: `src/main.tsx` (выбор платформы через `Capacitor.isNativePlatform()`), `MainActivity.java`, `package.json` (`@capacitor-community/sqlite`)
- Test: `src/platform/android/uploader.test.ts`

**Interfaces:**
- Consumes: Task 6 (`SqlExecutor`, `openSqliteStore`), Task 7 (`Uploader`), Task 9 (`AttachmentStore`), Task 5 (`AuthProvider`, `createStorage`), Task 10 (`Platform`), Task 11 (`StreamCipher`), Task 12 (плагины `Auth` и `Sync`, `OutboxDb`, `UploadScheduler`).
- Produces:
  - Kotlin `object KeySession { @Volatile var dek: ByteArray?; @Volatile var keyId: ByteArray?; fun clear() }`. Плагин `KeySession` (JS-имя): `setKey({ keyId /* hex */, dek /* base64url */ })`, `clear()`.
  - Плагин `Attachments` (JS-имя): `pick({ entryId }) → { refs: AttachmentRef[] }` (системный выбор фото и видео `PickMultipleVisualMedia`). Каждый файл потоково шифруется `StreamCipher` с контекстом `att:<id>` в `filesDir/att/<id>.mj`, затем ставится в `OutboxDb` строкой с ключом `ao/<id>` (тот же формат, что `attachmentKey` в TS), lane `attachment`, и вызывается `UploadScheduler.schedule`. Ещё методы: `readDecrypted({ attachmentId }) → { data /* base64url */ }` (на этом этапе только для фото), `storeCiphertext({ attachmentId, data })` и `has({ attachmentId }) → { value }`.
  - TS: `createAndroidPlatform(): Promise<Platform>`, где `store` = `openSqliteStore(new CapacitorSqlExecutor('diary'))`, `uploader` = `AndroidUploader` (обёртка над плагином `Sync`), `storage` = `createStorage('gdrive', { auth: обёртка над Auth-плагином })` (TS-часть плагина нужна при открытом приложении: приём изменений, проверка привязки, скачивание), `attachments` = `AndroidAttachmentStore` (`add(entryId, 'native-picker')` вызывает `Attachments.pick`; `readPlain`: если `has`, то `readDecrypted`, иначе `storage.backend.download` → `storeCiphertext` → `readDecrypted`), `onKeyUnlocked` вызывает `KeySession.setKey`, `setBinding` вызывает `Sync.setBinding`.
- Жизненный цикл: при событии `App` `pause` у открытой `EditorSession` вызвать `checkpoint()`, **не** `close()`: пауза наступает и при открытии системного выбора фото, после возврата запись продолжается в той же сессии. Затем `diary.sealAll()`, `diary.recover()` и `uploader.kick()`. При `resume` и перед каждой синхронизацией тоже вызывается `diary.recover()`. Блокировка по таймеру будет на этапе 2. Переключателя мобильной сети в интерфейсе на этом этапе нет, `setAllowMetered` проверяется на этапе 2 вместе с ним.
- Если `fetch` из WebView к `googleapis.com` упрётся в CORS, включить `CapacitorHttp` в `capacitor.config.ts` и записать это в отчёт задачи.

- [ ] **Step 1: Написать падающий тест** `uploader.test.ts` (плагин `Sync` подменяется через `vi.mock`)

```ts
test('enqueueBytes передаёт key, base64url-данные и lane', ...)
test('status, completed и ack пробрасываются как есть', ...)
```

- [ ] **Step 2: Запустить** `npx vitest run src/platform/android`. Ожидается FAIL.
- [ ] **Step 3: Реализовать** TS-адаптеры и Kotlin-плагины, зарегистрировать плагины.
- [ ] **Step 4: Запустить** `npx vitest run && npm run build && npx cap sync android && docker/gradle.sh :app:testDebugUnitTest assembleDebug`. Ожидается PASS и `BUILD SUCCESSFUL`.
- [ ] **Step 5: Commit** `Android: ключ, вложения, связка с TypeScript`.

---

### Task 14: Google Cloud, ключ подписи, релизный APK (вместе с пользователем)

**Files:**
- Create: `docs/setup/google-cloud.md`, `docs/setup/build.md`, `.env.local` (не коммитится)
- Modify: `android/app/build.gradle` (`signingConfigs.release` из переменных окружения `MJ_KEYSTORE`, `MJ_KEYSTORE_PASSWORD`, `MJ_KEY_ALIAS`), `docker/gradle.sh` (пробрасывает `MJ_*` и монтирует `~/.config/my-journey` в `/keys:ro`)

- [ ] **Step 1: Ключ подписи.** Сгенерировать пароль (`openssl rand -base64 24`) и сразу положить его в keyring командой `secret-tool store --label="My Journey release keystore" service my-journey kind keystore`, на экран не выводить. Создать `~/.config/my-journey/release.jks` (alias `myjourney`, RSA 4096, срок 36500 дней) через локальный `keytool`, пароль подставить из `secret-tool lookup service my-journey kind keystore`.
- [ ] **Step 2: Резервная копия ключа.** Спросить у владельца папку в его резервном хранилище и скопировать туда `release.jks`. Пароль туда не класть: он в keyring, при необходимости владелец запишет его сам.
- [ ] **Step 3: SHA-1 ключа** через `keytool -list -v -alias myjourney`. SHA-1 не секрет, его можно показать.
- [ ] **Step 4: Написать** `docs/setup/google-cloud.md` по шагам на русском: создать проект «Мой дневник»; включить Google Drive API; настроить экран согласия OAuth (тип External, область `.../auth/drive.appdata`, перевести в «In production»; проверить, требует ли Google верификации для этой области, и если требует, записать, как жить со статусом «Testing», где доступ истекает через 7 дней); создать OAuth-клиент «Веб-приложение» с JavaScript origin `http://localhost:4173`; создать OAuth-клиент «Android» с пакетом `io.github.bol970.myjourney` и SHA-1 из шага 3.
- [ ] **Step 5: Пройти шаги вместе с пользователем.** Консоль `https://console.cloud.google.com/` открывается в браузере владельца. Web client ID записать в `.env.local` как `VITE_GOOGLE_WEB_CLIENT_ID`.
- [ ] **Step 6: Релизная сборка:** `npm run build && npx cap sync android`, затем `MJ_KEYSTORE=/keys/release.jks MJ_KEY_ALIAS=myjourney MJ_KEYSTORE_PASSWORD="$(secret-tool lookup service my-journey kind keystore)" docker/gradle.sh assembleRelease`. Ожидается `android/app/build/outputs/apk/release/app-release.apk`. Проверить подпись через `apksigner verify --print-certs` в том же образе: SHA-1 совпадает с шагом 3.
- [ ] **Step 7: Написать** `docs/setup/build.md`: команды сборки, установка через `adb`, где лежат ключ и пароль.
- [ ] **Step 8: Commit** `Настройка Google Cloud и релизная сборка` (без `.env.local` и ключей).

---

### Task 15: Сквозная проверка: эмулятор и Chrome, затем телефон

**Предусловие:** включена VT-x. Проверка: `ls /dev/kvm`. Если файла нет, остановиться и напомнить пользователю включить Intel VT-x в BIOS. Эмулятор без этого не запустится.

**Files:**
- Create: `docs/superpowers/plans/2026-11-02-stage-1-results.md` (отчёт)
- Modify: `AGENTS.md` (раздел «Состояние»)

- [ ] **Step 1: Запуск.** Запустить в фоне `~/Android/Sdk/emulator/emulator -avd <AVD>`, где `<AVD>` это AVD с образом Google APIs и API 30+ (список: `emulator -list-avds`). Пользователь сам входит в свой Google-аккаунт в настройках эмулятора. Установить APK: `~/Android/Sdk/platform-tools/adb install -r android/app/build/outputs/apk/release/app-release.apk`. Положить в эмулятор тестовое JPEG на 1–3 МБ (сгенерировать, **не из архива Journey**) через `adb push … /sdcard/Pictures/` и `adb shell content call --method scan_volume --uri content://media --arg external_primary`.
- [ ] **Step 2: Сценарий А, телефон → компьютер → телефон.**
  1. На эмуляторе: подключить Google, создать дневник, сохранить ключ восстановления. Создать запись «Проверка 1», нажать «Фото или видео», выбрать фото, вернуться и дописать в той же записи «и после фото». Выйти из редактора. Ожидается: в записи и текст до фото, и «и после фото», и само фото.
  2. В Chrome: `npm run preview`, открыть `http://localhost:4173` через `open-link`, подключить тот же Google-аккаунт, ввести тот же пароль. Ожидается запись «Проверка 1», фото открывается.
  3. В Chrome поменять текст на «Проверка 1, правка с компьютера» и выйти из редактора.
  4. На эмуляторе открыть приложение. Ожидается новый текст.
- [ ] **Step 3: Сценарий Б, фоновая отправка после перезагрузки.**
  1. **Сначала** выключить сеть: `adb shell svc wifi disable && adb shell svc data disable`.
  2. На эмуляторе создать запись «Фон» с фото и выйти из редактора. Убедиться, что строка синхронизации показывает «Отправляется: 2» (запись и фото), а в Chrome после синхронизации записи «Фон» нет. Иначе проверка ничего не докажет: маленькое фото может успеть уйти до перезагрузки.
  3. Нажать «Домой», затем `adb reboot`.
  4. После загрузки: `adb shell svc wifi enable`. Приложение **не открывать**.
  5. Подождать до 15 минут. В Chrome запись «Фон» с фото появляется.
- [ ] **Step 4: Сценарий В, конфликт.** Эмулятор в режиме полёта, Chrome через DevTools → Network → Offline. Одну запись поправить по-разному на обоих. Вернуть сеть. Ожидается отметка «Конфликт» на обоих. Разрешить в Chrome, после синхронизации на эмуляторе конфликта нет.
- [ ] **Step 5: Сценарий Г, пароль и ключ.** Неверный пароль даёт «Неверный пароль». В Chrome очистить данные сайта и войти по ключу восстановления. Ожидается полный список записей.
- [ ] **Step 5a: Сценарий Д, другой аккаунт.** В Chrome создать запись без сети, затем нажать «Переподключить» и выбрать **другой** Google-аккаунт (у пользователя спросить, какой можно использовать). Ожидается предупреждение о другом аккаунте, а в другом аккаунте ничего не появляется. После переподключения нужного аккаунта запись уходит.
- [ ] **Step 6: Реальный телефон владельца.** Попросить владельца включить отладку по USB и подключить телефон (или передать APK файлом). Повторить сценарии А и Б с настоящей камерой и фото. Записать, как прошивка обращается с фоновой отправкой без исключения из оптимизации батареи: это входные данные для этапа 2.
- [ ] **Step 7: Записать результаты** в `2026-11-02-stage-1-results.md` (что прошло, что нет, с выводами команд) и обновить раздел «Состояние» в `AGENTS.md`.
- [ ] **Step 8: Commit** `Этап 1: сквозная проверка`.

---

## Дальнейшие этапы (отдельные планы после этапа 1)

Каждый этап получит свой план в `docs/superpowers/plans/`, когда предыдущий готов. Интерфейсы этапа 1 к тому моменту станут фактом.

- **Этап 2. Дневник целиком.** Полный редактор (ссылки, списки), заголовок, дата и пояс. Лента с виртуальным списком и превью (генерация и синхронизация превью, на Android нативно, включая HEIC). Календарь, поиск (ё=е, по началу слова, индекс в фоне), теги и группы (раздел 6.2а: справочник, переадресация, экран тегов), настроение, место (Nominatim), погода (Open-Meteo), корзина с окончательным удалением и надгробиями. Видео: съёмка через `ACTION_VIDEO_CAPTURE`, воспроизведение с перемоткой без полной расшифровки, кэш скачанных файлов на 2 ГБ. Разблокировка отпечатком через Android Keystore, автоблокировка (5 минут в фоне, 15 минут на компьютере), смена пароля, новый ключ восстановления, переключатель мобильной сети, запрос исключения из оптимизации батареи, темы, счётчик места на Drive.
- **Этап 3. Карта.** Отдельный экран, группировка около 4600 точек, подложка OSM, список записей по точке.
- **Этап 4. Импорт Journey.** Потоковое чтение ZIP с сетевого хранилища, детерминированные идентификаторы, возобновляемость, сопоставление `mood` вместе с владельцем, теги (выбранные на экране импорта становятся группами, склейки галочками), часовой пояс по умолчанию для пустых `timezone`, отчёт со сверкой по `docs/research/journey_stats.py`.
- **Этап 5. Экспорт, восстановление и поставка.** Экспорт по периодам на сетевое хранилище, просмотр и загрузка экспорта в подключённое хранилище, объект состояния телефона, запускатель (Node-сервер на `127.0.0.1:4173` и `.desktop`-файл), финальная инструкция.
- **После первой версии: другие хранилища.** Новые плагины (WebDAV, в том числе NAS и Яндекс.Диск, затем другие) по контракту из Task 5: TS-часть проходит `backendContract`, Kotlin-часть повторяет протокол загрузки. Для хранилищ, к которым браузер не может обратиться напрямую (FTP, WebDAV без CORS), отдельно решается вопрос посредника в локальном запускателе. Выбор хранилища появляется на экране подключения вместе со вторым плагином.

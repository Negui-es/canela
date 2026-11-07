# Canela · Tu cuaderno de cerámica

Canela es una aplicación web para llevar el cuaderno de un taller de cerámica. Permite documentar piezas y sus avances, organizar materiales y recetas, compartir recursos con otros miembros del taller y preparar galerías con las fotografías que quieras publicar.

Puedes instalar tu propia instancia en un ordenador o servidor. La aplicación comienza vacía y cada instalación mantiene sus propias cuentas, piezas y fotografías.

## Qué puedes hacer

- Registrar piezas, técnicas, dimensiones, etiquetas y etapas de trabajo, desde el modelado hasta la pieza terminada.
- Anotar avances y aplicaciones de esmalte, con cantidades, capas, zonas y versiones de recetas.
- Organizar barros, esmaltes, engobes, moldes y pruebas de materiales, incluyendo su disponibilidad.
- Añadir y ordenar fotografías y elegir la portada de cada pieza o prueba.
- Crear talleres y subgrupos y decidir con quién compartir cada recurso.
- Preparar una presentación pública con textos y fotos seleccionados, reutilizarla en galerías y publicarla en Inspiración.
- Consultar la interfaz en español, inglés, francés, alemán o italiano desde ordenador y móvil.

Las fichas, notas y fotografías privadas requieren los permisos correspondientes. Las galerías públicas e Inspiración muestran la presentación que su propietario ha elegido publicar. Las recetas y el historial de trabajo permanecen en su ámbito privado o compartido.

Canela se puede instalar como aplicación web en el móvil mediante HTTPS. Sigue necesitando conexión para consultar y guardar contenido. Su pantalla de desconexión conserva únicamente recursos genéricos.

## Instalación con Docker Compose

Necesitas Git, Docker y Docker Compose. Docker Desktop incluye Compose en Windows y macOS. El contenedor de la aplicación utiliza Python 3.12 y Django 5.2 LTS y se conecta a PostgreSQL 17.

```sh
git clone https://github.com/Negui-es/canela.git
cd canela
cp .env.example .env
```

En Windows también puedes copiar el archivo desde el explorador o utilizar `Copy-Item .env.example .env` en PowerShell.

Edita `.env` y asigna valores aleatorios diferentes a `POSTGRES_PASSWORD` y `SECRET_KEY`. Puedes generar cada uno ejecutando esta orden con Python instalado.

```sh
python -c "import secrets; print(secrets.token_urlsafe(48))"
```

El archivo de ejemplo está preparado para acceder por HTTP desde el mismo ordenador. Arranca los servicios y crea la primera cuenta administradora.

```sh
docker compose up --build -d
docker compose exec web python manage.py createsuperuser
docker compose ps
```

Abre [http://127.0.0.1:8000](http://127.0.0.1:8000). Introduce el usuario y la contraseña que acabas de crear. El arranque aplica las migraciones y espera a que PostgreSQL esté disponible. No hay una cuenta ni una contraseña predeterminadas.

## Configuración de una instancia pública

Configura un dominio propio y un proxy HTTPS o un túnel que conecte con la aplicación. Por ejemplo, para `ceramica.example.org`, cambia estas opciones de `.env`.

```dotenv
DEBUG=0
ALLOWED_HOSTS=ceramica.example.org,localhost,127.0.0.1
CSRF_TRUSTED_ORIGINS=https://ceramica.example.org
TRUST_PROXY=1
ALLOW_NEW_ACCOUNTS=0
```

`ALLOWED_HOSTS` contiene nombres de host separados por comas. `CSRF_TRUSTED_ORIGINS` contiene los orígenes completos con `https://`. Activa `TRUST_PROXY` cuando el tráfico llegue a través de tu proxy de confianza y configura ese proxy para conservar el host y enviar `X-Forwarded-Proto: https`.

El Compose publica la web únicamente en `127.0.0.1:8000` del servidor. Un proxy o `cloudflared` instalado en ese mismo servidor puede utilizar esa dirección. Si el proxy es otro contenedor, conéctalo a la red de Compose y utiliza `http://web:8000`. PostgreSQL se comunica por la red interna de Docker.

Aplica la configuración y comprueba Django.

```sh
docker compose up -d
docker compose exec web python manage.py check --deploy
```

Con `DEBUG=0`, Canela exige HTTPS y utiliza cookies seguras. El acceso HTTP directo de loopback se conserva para administración local. La comprobación de salud está en `/health/`.

## Cuentas, permisos e idiomas

La primera cuenta de producción se crea con `createsuperuser`. Las altas mediante invitación están cerradas por defecto. Para permitir que una persona con cuenta genere invitaciones desde «Mi cuenta», establece `ALLOW_NEW_ACCOUNTS=1` y recrea el servicio con `docker compose up -d`. Las invitaciones son de un solo uso y caducan a los siete días. Crear un enlace para incorporarse a un taller y permitir crear una cuenta son operaciones distintas.

Cada persona conserva la propiedad de sus piezas. Los talleres permiten compartir recursos y organizar miembros y administradores. La publicación de una presentación se realiza expresamente desde la ficha de la pieza.

La dirección `/` elige el idioma según las preferencias del navegador. También puedes entrar por `/es/`, `/en/`, `/fr/`, `/de/` o `/it/`. Los nombres, las notas y los demás textos que escriben los usuarios se conservan en su idioma original.

## Datos y copias de seguridad

| Almacenamiento | Contenido |
| --- | --- |
| Volumen `database` | Usuarios, contraseñas derivadas mediante hash, sesiones, piezas, materiales, recetas, grupos y metadatos de fotos |
| Volumen `photos` | Archivos originales de fotografías y sus versiones procesadas |
| Volumen `runtime` | Directorio de trabajo persistente de la aplicación |
| `.env` | Secretos y configuración de tu instalación |

Una copia completa necesita la base de datos, las fotografías y los secretos. Las fotografías se almacenan como archivos, con sus referencias en la base de datos. Conserva estos elementos fuera del repositorio público y guarda un respaldo en otro equipo o almacenamiento.

Para crear una copia portable, suspende las ediciones mientras se realiza la operación.

```sh
docker compose exec web python scripts/backup.py
docker compose cp web:/app/backups ./backups
```

Cada ZIP contiene `database.json` y `media/`. El archivo JSON contiene datos privados y hashes de contraseñas. Este formato omite sesiones, registros del administrador y permisos generados por Django. Conserva `.env` por separado.

Para restaurar o trasladar esa copia, utiliza una instalación compatible con una base vacía, aplica las migraciones y extrae el ZIP en una carpeta privada. Antes de crear cuentas, importa sus datos y copia sus fotos.

```sh
docker compose cp ./restauracion/database.json web:/app/data/database.json
docker compose exec web python manage.py loaddata /app/data/database.json
docker compose cp ./restauracion/media/. web:/app/media/
```

En Linux, comprueba que el usuario del contenedor, UID 10001, pueda leer y escribir los archivos restaurados. Verifica el inicio de sesión y el acceso a las fotos después del traslado. Para una recuperación con sesiones y registros completos, utiliza un respaldo nativo de PostgreSQL junto con el volumen de fotos.

## Actualizar

Guarda una copia antes de actualizar y revisa si la nueva versión incorpora migraciones.

```sh
git pull --ff-only
docker compose up --build -d
docker compose ps
docker compose logs --tail=50 web
```

Los volúmenes sobreviven a la sustitución de contenedores. `docker compose down -v` elimina los volúmenes y sus datos. Recuperar una imagen anterior no deshace las migraciones de base de datos.

## Desarrollo local y pruebas

También puedes desarrollar con Python 3.12 y SQLite. Crea un entorno virtual, actívalo e instala las dependencias.

```sh
python -m venv .venv
# Linux y macOS
source .venv/bin/activate
# Windows PowerShell
# .venv\Scripts\Activate.ps1
python -m pip install -r requirements.txt
python run_local.py
```

Este lanzador usa SQLite en `data/canela.sqlite3`, fotografías en `media/` y una clave local en `.local-secret`. Abre [http://127.0.0.1:8000](http://127.0.0.1:8000). En desarrollo, la primera cuenta también puede crearse desde la configuración inicial local. El lanzador de Windows `Iniciar Canela.cmd` utiliza ese mismo entorno virtual.

Puedes ejecutar la batería de Django contra PostgreSQL en una instancia de desarrollo vacía.

```sh
docker compose exec web python manage.py test studio --noinput
```

La cuenta de PostgreSQL utilizada por las pruebas necesita permiso para crear una base temporal. Las pruebas usan datos sintéticos.

Los recursos de interfaz compilados se incluyen en Git. Para cambiarlos necesitas Node.js y pnpm.

```sh
pnpm install --frozen-lockfile
pnpm run build
node --test scripts/test-pwa.cjs
```

Los catálogos de traducción están en `locale/`. Ejecuta `python scripts/build_translations.py` después de editarlos. Docker y el lanzador local los compilan automáticamente. La compilación utiliza `polib` y no necesita GNU gettext instalado.

## Organización del código

| Carpeta | Responsabilidad |
| --- | --- |
| `canela/` | Configuración de Django, seguridad, idiomas y aplicación instalable |
| `studio/` | Modelos, permisos, formularios, vistas, migraciones y pruebas del taller |
| `templates/` | Pantallas y componentes HTML |
| `static/`, `frontend/` | Estilos, JavaScript, iconos y dependencias del navegador |
| `locale/` | Traducciones de interfaz y rutas |
| `scripts/` | Arranque, compilación, auditoría y copias de seguridad |

## Licencia

El código de Canela se distribuye bajo la licencia MIT. Las dependencias mantienen sus propias licencias, indicadas en `THIRD_PARTY_NOTICES.md`.

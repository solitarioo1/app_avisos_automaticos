# Estructura CSS - La Positiva AgroSeguros

## Organización de Archivos

La estructura CSS está categorizada para facilitar el mantenimiento y escalabilidad:

```
static/css/
├── main.css                 # Archivo maestro que importa todos
├── 1-colores.css           # Paleta de colores corporativos
├── 2-variables.css         # Variables CSS (espaciado, tipografía, etc)
├── 3-mixins.css            # Utilidades y clases reutilizables
├── 4-generales.css         # Estilos base globales
├── inicio.css              # Página de bienvenida
├── avisos.css              # Página de gestión de avisos
├── mapas.css               # Página de mapas meteorológicos
├── dashboard.css           # Panel de control principal
├── decisiones.css          # Centro de toma de decisiones
├── whatsapp.css            # Módulo de WhatsApp masivo
└── style.css               # (DEPRECADO - usar main.css)
```

## Cómo usar

### En templates HTML
```html
<!-- base.html ya importa main.css -->
<link href="{{ url_for('static', filename='css/main.css') }}" rel="stylesheet">
```

### Agregar nuevas páginas
1. Crear archivo CSS específico: `static/css/nueva-pagina.css`
2. Agregar import en `main.css`: `@import url('./nueva-pagina.css');`
3. Los colores, variables y mixins estarán disponibles automáticamente

## Variables disponibles

### Colores
```css
--primary-color: #04ccc4          /* Turquesa */
--accent-light: #fa6f4a           /* Naranja */
--success: #28a745                /* Verde */
--warning: #ffc107                /* Amarillo */
--danger: #dc3545                 /* Rojo */
```

### Espaciado
```css
--spacing-xs: 4px
--spacing-sm: 8px
--spacing-md: 12px
--spacing-lg: 15px
--spacing-xl: 20px
```

### Tipografía
```css
--font-size-base: 14px
--font-size-sm: 12px
--font-size-h1: 28px
--font-size-h2: 22px
```

## Ejemplo de uso en CSS específico

```css
/* En archivo nuevo static/css/nueva-pagina.css */

.mi-componente {
    background: var(--white);
    color: var(--text-primary);
    padding: var(--spacing-lg);
    border-radius: var(--border-radius);
    border: var(--border-width) solid var(--border-color);
    transition: all var(--transition-base);
}

.mi-componente:hover {
    box-shadow: var(--shadow-lg);
}
```

## Mantenimiento

- **Cambiar colores**: Editar `1-colores.css`
- **Ajustar espaciado**: Editar `2-variables.css`
- **Agregar utilidades**: Editar `3-mixins.css`
- **Cambios globales**: Editar `4-generales.css`
- **Cambios específicos de página**: Editar archivo correspondiente

## Beneficios

✅ Fácil mantenimiento
✅ Colores consistentes
✅ Variables reutilizables
✅ Separación por responsabilidad
✅ Escalabilidad
✅ Rendimiento optimizado

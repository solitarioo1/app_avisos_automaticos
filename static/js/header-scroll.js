// Control de scroll - Header desaparece, Nav permanece
let lastScrollY = 0;
const header = document.querySelector('.main-header');
const nav = document.querySelector('.main-navigation');

window.addEventListener('scroll', () => {
    const currentScrollY = window.scrollY;
    
    if (currentScrollY > lastScrollY && currentScrollY > 100) {
        // Scrolleando hacia abajo - Ocultar header, nav sube
        header.style.top = '-100px';
        nav.style.top = '0px';
    } else {
        // Scrolleando hacia arriba - Mostrar header, nav vuelve a posición
        header.style.top = '0px';
        nav.style.top = '75px';
    }
    
    lastScrollY = currentScrollY;
});

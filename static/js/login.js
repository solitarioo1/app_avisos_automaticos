function togglePassword() {
    const field = document.getElementById('password-field');
    const icon  = document.getElementById('pw-icon');
    if (field.type === 'password') {
        field.type = 'text';
        icon.classList.replace('bi-eye-fill', 'bi-eye-slash-fill');
    } else {
        field.type = 'password';
        icon.classList.replace('bi-eye-slash-fill', 'bi-eye-fill');
    }
}

/**
 * SIAKRED - Login Page Interactions
 * - Password show/hide toggle
 * - Password strength meter
 * - Form submit loading state
 * - CAPTCHA focus enhancement
 */

document.addEventListener('DOMContentLoaded', function () {

  // ==========================================
  // PASSWORD TOGGLE
  // ==========================================
  const passwordInput = document.getElementById('id_password');
  const passwordToggle = document.getElementById('password-toggle');
  const iconEye = document.getElementById('icon-eye');
  const iconEyeOff = document.getElementById('icon-eye-off');

  if (passwordToggle && passwordInput) {
    passwordToggle.addEventListener('click', function () {
      const isPassword = passwordInput.type === 'password';
      passwordInput.type = isPassword ? 'text' : 'password';
      if (iconEye && iconEyeOff) {
        iconEye.style.display = isPassword ? 'none' : 'block';
        iconEyeOff.style.display = isPassword ? 'block' : 'none';
      }
      passwordToggle.setAttribute('aria-label',
        isPassword ? 'Sembunyikan password' : 'Tampilkan password'
      );
    });
  }

  // ==========================================
  // PASSWORD STRENGTH METER
  // ==========================================
  const strengthMeter = document.getElementById('password-strength');
  const strengthBar = document.getElementById('password-strength-bar');
  const strengthLabel = document.getElementById('password-strength-label');

  function calculateStrength(password) {
    if (!password) return { score: 0, label: '', className: '' };

    let score = 0;
    if (password.length >= 6) score++;
    if (password.length >= 10) score++;
    if (/[A-Z]/.test(password)) score++;
    if (/[0-9]/.test(password)) score++;
    if (/[^A-Za-z0-9]/.test(password)) score++;

    if (score <= 2) return { score: 1, label: 'Lemah', className: 'weak' };
    if (score === 3 || score === 4) return { score: 2, label: 'Cukup', className: 'medium' };
    return { score: 3, label: 'Kuat', className: 'strong' };
  }

  if (passwordInput && strengthMeter && strengthBar && strengthLabel) {
    passwordInput.addEventListener('input', function () {
      const value = this.value;
      if (!value) {
        strengthMeter.classList.remove('active');
        strengthLabel.classList.remove('active');
        return;
      }

      const result = calculateStrength(value);
      strengthMeter.classList.add('active');
      strengthLabel.classList.add('active');
      strengthBar.className = 'password-strength-bar ' + result.className;
      strengthLabel.textContent = 'Kekuatan: ' + result.label;
    });
  }

  // ==========================================
  // FORM SUBMIT LOADING STATE
  // ==========================================
  const loginForm = document.getElementById('login-form');
  const submitBtn = document.getElementById('submit-btn');

  if (loginForm && submitBtn) {
    loginForm.addEventListener('submit', function () {
      submitBtn.classList.add('btn-loading');
      submitBtn.disabled = true;
    });
  }

  // ==========================================
  // CAPS LOCK WARNING
  // ==========================================
  const capsWarning = document.getElementById('caps-warning');

  if (passwordInput && capsWarning) {
    passwordInput.addEventListener('keyup', function (e) {
      if (e.getModifierState && e.getModifierState('CapsLock')) {
        capsWarning.style.display = 'flex';
      } else {
        capsWarning.style.display = 'none';
      }
    });

    passwordInput.addEventListener('blur', function () {
      capsWarning.style.display = 'none';
    });
  }

  // ==========================================
  // CAPTCHA: Auto-focus ketika muncul
  // ==========================================
  const captchaInput = document.querySelector('.captcha-input');
  if (captchaInput) {
    // Scroll ke captcha kalau muncul karena gagal login
    const captchaBox = document.querySelector('.captcha-box');
    if (captchaBox) {
      setTimeout(function () {
        captchaBox.scrollIntoView({ behavior: 'smooth', block: 'center' });
      }, 300);
    }
  }

});
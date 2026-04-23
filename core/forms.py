"""
Forms untuk app core.
"""
import random
import hashlib

from django import forms
from django.contrib.auth import authenticate, get_user_model
from django.db.models import Q
from django.utils.translation import gettext_lazy as _


User = get_user_model()


# ============================================
# CAPTCHA MATEMATIKA
# ============================================

class MathCaptcha:
    OPERATIONS = [
        ("+", lambda a, b: a + b),
        ("-", lambda a, b: a - b),
        ("×", lambda a, b: a * b),
    ]

    @classmethod
    def generate(cls):
        op_symbol, op_func = random.choice(cls.OPERATIONS)

        if op_symbol == "×":
            a = random.randint(2, 9)
            b = random.randint(2, 9)
        elif op_symbol == "-":
            a = random.randint(10, 30)
            b = random.randint(1, a)
        else:
            a = random.randint(1, 20)
            b = random.randint(1, 20)

        question = f"{a} {op_symbol} {b}"
        answer = op_func(a, b)
        token = cls._make_token(question, answer)
        return question, answer, token

    @staticmethod
    def _make_token(question, answer):
        raw = f"{question}|{answer}|siakred-captcha-salt"
        return hashlib.sha256(raw.encode()).hexdigest()[:32]

    @classmethod
    def verify(cls, question, user_answer, token):
        try:
            user_answer_int = int(user_answer)
        except (ValueError, TypeError):
            return False
        expected_token = cls._make_token(question, user_answer_int)
        return expected_token == token


# ============================================
# LOGIN FORM
# ============================================

class LoginForm(forms.Form):
    identifier = forms.CharField(
        label=_("Username / Email"),
        max_length=200,
        error_messages={
            "required": _("Username atau email wajib diisi."),
        },
    )

    password = forms.CharField(
        label=_("Password"),
        widget=forms.PasswordInput(),
        error_messages={
            "required": _("Password wajib diisi."),
        },
    )

    remember_me = forms.BooleanField(
        label=_("Ingat saya"),
        required=False,
        initial=False,
    )

    captcha_question = forms.CharField(required=False, widget=forms.HiddenInput())
    captcha_token = forms.CharField(required=False, widget=forms.HiddenInput())
    captcha_answer = forms.CharField(
        label=_("Verifikasi"),
        required=False,
    )

    def __init__(self, *args, request=None, require_captcha=False, **kwargs):
        self.request = request
        self.require_captcha = require_captcha
        self.user_cache = None
        super().__init__(*args, **kwargs)

        if not require_captcha:
            self.fields.pop("captcha_question", None)
            self.fields.pop("captcha_token", None)
            self.fields.pop("captcha_answer", None)

    def clean(self):
        cleaned_data = super().clean()
        identifier = cleaned_data.get("identifier", "").strip()
        password = cleaned_data.get("password", "")

        if self.require_captcha:
            question = cleaned_data.get("captcha_question", "")
            token = cleaned_data.get("captcha_token", "")
            answer = cleaned_data.get("captcha_answer", "").strip()

            if not answer:
                raise forms.ValidationError(
                    _("Jawaban verifikasi wajib diisi."),
                    code="captcha_required",
                )

            if not MathCaptcha.verify(question, answer, token):
                raise forms.ValidationError(
                    _("Jawaban verifikasi salah. Silakan coba lagi."),
                    code="captcha_invalid",
                )

        if not identifier or not password:
            return cleaned_data

        user_obj = None
        try:
            user_obj = User.objects.get(
                Q(username__iexact=identifier) | Q(email__iexact=identifier)
            )
        except User.DoesNotExist:
            pass
        except User.MultipleObjectsReturned:
            user_obj = User.objects.filter(username__iexact=identifier).first()

        if not user_obj:
            raise forms.ValidationError(
                _("Username/email atau password salah."),
                code="invalid_login",
            )

        user = authenticate(
            self.request,
            username=user_obj.username,
            password=password,
        )

        if user is None:
            raise forms.ValidationError(
                _("Username/email atau password salah."),
                code="invalid_login",
            )

        if not user.is_active:
            raise forms.ValidationError(
                _("Akun Anda tidak aktif. Hubungi administrator."),
                code="inactive",
            )

        self.user_cache = user
        return cleaned_data

    def get_user(self):
        return self.user_cache
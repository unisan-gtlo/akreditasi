/**
 * SIAKRED — Copy Link Public Handler
 * 
 * Listen klik tombol .btn-copy-link, copy URL ke clipboard,
 * lalu kasih feedback visual + toast notification.
 * 
 * Usage:
 *   Include script ini di template yang punya tombol Copy Link:
 *   <script src="{% static 'js/copy-link.js' %}" defer></script>
 */

(function () {
    'use strict';

    /* === Toast notification === */
    function showToast(msg, type) {
        type = type || 'success';
        var existing = document.getElementById('siakred-copy-toast');
        if (existing) existing.remove();

        var toast = document.createElement('div');
        toast.id = 'siakred-copy-toast';
        toast.textContent = msg;
        toast.style.cssText = [
            'position:fixed',
            'bottom:24px',
            'right:24px',
            'padding:.85rem 1.25rem',
            'background:' + (type === 'success' ? '#10B981' : '#EF4444'),
            'color:white',
            'border-radius:10px',
            'font-size:.9rem',
            'font-weight:600',
            'box-shadow:0 8px 24px rgba(0,0,0,.18)',
            'z-index:9999',
            'opacity:0',
            'transform:translateY(10px)',
            'transition:opacity .2s, transform .2s',
            'max-width:380px'
        ].join(';');
        document.body.appendChild(toast);

        // Trigger animation
        requestAnimationFrame(function () {
            toast.style.opacity = '1';
            toast.style.transform = 'translateY(0)';
        });

        // Auto-dismiss after 3s
        setTimeout(function () {
            toast.style.opacity = '0';
            toast.style.transform = 'translateY(10px)';
            setTimeout(function () { toast.remove(); }, 250);
        }, 3000);
    }

    /* === Copy fallback untuk browser lama === */
    function fallbackCopy(text) {
        var ta = document.createElement('textarea');
        ta.value = text;
        ta.style.position = 'fixed';
        ta.style.opacity = '0';
        document.body.appendChild(ta);
        ta.select();
        var ok = false;
        try { ok = document.execCommand('copy'); } catch (e) { ok = false; }
        document.body.removeChild(ta);
        return ok;
    }

    /* === Main handler === */
    document.addEventListener('click', function (e) {
        var btn = e.target.closest('.btn-copy-link');
        if (!btn) return;

        var link = btn.dataset.link;
        var name = btn.dataset.name || 'dokumen';
        if (!link) return;

        var done = function (ok) {
            if (ok) {
                btn.classList.add('copied');
                setTimeout(function () { btn.classList.remove('copied'); }, 1800);
                showToast('Link "' + name + '" disalin ke clipboard', 'success');
            } else {
                showToast('Gagal menyalin. Copy manual: ' + link, 'error');
                window.prompt('Copy link berikut secara manual:', link);
            }
        };

        // Modern API (HTTPS only)
        if (navigator.clipboard && navigator.clipboard.writeText) {
            navigator.clipboard.writeText(link).then(
                function () { done(true); },
                function () { done(fallbackCopy(link)); }
            );
        } else {
            done(fallbackCopy(link));
        }
    });
})();
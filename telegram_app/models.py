from django.db import models


class TelegramMessage(models.Model):
    """Protokoll aller über die zentrale Telegram-API-Funktion versendeten Nachrichten."""

    message = models.TextField('Nachricht')
    trigger = models.CharField(
        'Trigger',
        max_length=64,
        blank=True,
        default='',
        help_text='Für zukünftige automatische Auslöser (z.B. Event-Name). Aktuell ungenutzt.',
    )
    sent_at = models.DateTimeField('Gesendet am', auto_now_add=True)

    class Meta:
        verbose_name = 'Telegram-Nachricht'
        verbose_name_plural = 'Telegram-Nachrichten'
        ordering = ['-sent_at']

    def __str__(self):
        preview = self.message if len(self.message) <= 50 else self.message[:50] + '…'
        return f"{self.sent_at:%d.%m.%Y %H:%M} – {preview}"

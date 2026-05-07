import requests
from bs4 import BeautifulSoup
from datetime import date
from django.core.management.base import BaseCommand
from apps.finanzas.models import TasaCambio, Moneda
from django.contrib.auth import get_user_model

BCV_URL = "https://www.bcv.org.ve/"

class Command(BaseCommand):
    help = 'Actualiza la tasa de cambio OFICIAL_BCV desde la web del BCV.'

    def handle(self, *args, **options):
        self.stdout.write('Obteniendo tasa de cambio USD desde BCV...')

        resp = requests.get(BCV_URL, timeout=20, verify=False)
        html = resp.text
        # Guardar HTML para depuración
        with open('bcv_debug.html', 'w', encoding='utf-8') as f:
            f.write(html)

        soup = BeautifulSoup(html, 'html.parser')

        # Extraer tasa USD/VES
        usd_value = None
        usd_div = soup.find('div', id='dolar')
        if usd_div:
            strong = usd_div.find('strong')
            if strong:
                usd_rate_str = strong.text.strip().replace('.', '').replace(',', '.')
                try:
                    usd_value = float(usd_rate_str)
                except Exception as e:
                    self.stderr.write(f'Error al convertir la tasa USD/VES: {usd_rate_str} - {e}')
            else:
                self.stderr.write('No se encontró el elemento <strong> dentro de #dolar.')
        else:
            self.stderr.write("No se pudo encontrar el div con id 'dolar' en la página.")

        # Extraer tasa EUR/VES (opcional, si existe)
        eur_value = None
        eur_div = soup.find('div', id='euro')
        if eur_div:
            strong = eur_div.find('strong')
            if strong:
                eur_rate_str = strong.text.strip().replace('.', '').replace(',', '.')
                try:
                    eur_value = float(eur_rate_str)
                except Exception as e:
                    self.stderr.write(f'Error al convertir la tasa EUR/VES: {eur_rate_str} - {e}')
            else:
                self.stderr.write('No se encontró el elemento <strong> dentro de #euro.')

        if not usd_value:
            self.stderr.write('No se pudo extraer el valor numérico de USD.')
        if not eur_value:
            self.stderr.write('No se pudo extraer el valor numérico de EUR.')
        if not usd_value and not eur_value:
            return

        # Extraer la fecha de la tasa
        tasa_fecha = None
        fecha_valor_div = soup.find('div', class_='pull-right dinpro center')
        if fecha_valor_div:
            date_span = fecha_valor_div.find('span', class_='date-display-single')
            if date_span and date_span.has_attr('content'):
                tasa_fecha = date_span['content'][:10]
                self.stdout.write(self.style.SUCCESS(f"Fecha de la tasa encontrada: {tasa_fecha}"))
            else:
                self.stderr.write("No se encontró el span con la fecha de la tasa.")
        else:
            self.stderr.write("No se pudo encontrar el div con la fecha de la tasa.")

        # Buscar monedas
        try:
            moneda_usd = Moneda.objects.get(codigo_iso='USD')
            moneda_eur = Moneda.objects.get(codigo_iso='EUR')
            moneda_ves = Moneda.objects.get(codigo_iso='VES')
        except Moneda.DoesNotExist:
            self.stderr.write('No se encontró la moneda USD, EUR o VES en la base de datos.')
            return

        # Usuario sistema (puedes ajustar esto)
        User = get_user_model()
        usuario = User.objects.filter(is_superuser=True).first()

        # Guardar USD/VES como tasa global (id_empresa=None)
        if usd_value:
            tasa_usd, created_usd = TasaCambio.objects.update_or_create(
                fecha_tasa=date.today(),
                id_moneda_origen=moneda_usd,
                id_moneda_destino=moneda_ves,
                tipo_tasa='OFICIAL_BCV',
                id_empresa=None,
                defaults={
                    'valor_tasa': usd_value,
                    'id_usuario_registro': usuario,
                }
            )
            if created_usd:
                self.stdout.write(self.style.SUCCESS(f'Tasa USD/VES OFICIAL_BCV creada: {usd_value}'))
            else:
                self.stdout.write(self.style.SUCCESS(f'Tasa USD/VES OFICIAL_BCV actualizada: {usd_value}'))

        # Guardar EUR/VES como tasa global (id_empresa=None)
        if eur_value:
            tasa_eur, created_eur = TasaCambio.objects.update_or_create(
                fecha_tasa=date.today(),
                id_moneda_origen=moneda_eur,
                id_moneda_destino=moneda_ves,
                tipo_tasa='OFICIAL_BCV',
                id_empresa=None,
                defaults={
                    'valor_tasa': eur_value,
                    'id_usuario_registro': usuario,
                }
            )
            if created_eur:
                self.stdout.write(self.style.SUCCESS(f'Tasa EUR/VES OFICIAL_BCV creada: {eur_value}'))
            else:
                self.stdout.write(self.style.SUCCESS(f'Tasa EUR/VES OFICIAL_BCV actualizada: {eur_value}'))

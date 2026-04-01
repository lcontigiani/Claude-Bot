"""
Modulo de generacion de cotizaciones para empresa de oficina.
Genera presupuestos formales con calculo de IVA, descuentos y numeracion automatica.
"""

import uuid
import random
from datetime import datetime, timezone, timedelta


# Prefijo de la empresa para los numeros de cotizacion
_EMPRESA_PREFIX = "COT"

# IVA estandar (21%)
_IVA_RATE = 0.21


def _generar_numero_cotizacion() -> str:
    """Genera un numero de cotizacion unico con formato COT-YYYYMM-XXXX."""
    ahora = datetime.now(timezone.utc)
    # Combinamos ano/mes + 4 digitos aleatorios para evitar colisiones
    sufijo = random.randint(1000, 9999)
    return f"{_EMPRESA_PREFIX}-{ahora.strftime('%Y%m')}-{sufijo}"


def generar_cotizacion(
    cliente_nombre: str,
    cliente_empresa: str,
    items: list,
    moneda: str = "USD",
    descuento_pct: float = 0.0,
    notas: str = "",
) -> dict:
    """Genera una cotizacion formal para un cliente corporativo.

    Calcula subtotales por linea, aplica descuento global, agrega IVA (21%)
    y produce un documento estructurado listo para presentar al cliente.

    Args:
        cliente_nombre: Nombre completo del contacto en el cliente.
            Ejemplo: "Juan Perez"
        cliente_empresa: Razon social o nombre comercial de la empresa cliente.
            Ejemplo: "Distribuidora Norte S.A."
        items: Lista de productos/servicios a cotizar. Cada elemento debe ser
            un diccionario con las claves:
            - producto (str): Nombre o descripcion del producto/servicio.
            - cantidad (int): Unidades requeridas. Debe ser mayor a 0.
            - precio_unitario (float): Precio por unidad sin impuestos, en la moneda indicada.
            Ejemplo: [{"producto": "Papel A4 500 hojas", "cantidad": 10, "precio_unitario": 5.50}]
        moneda: Codigo de moneda ISO 4217 para todos los importes.
            Valores validos: "USD", "EUR", "ARS", "MXN". Por defecto "USD".
        descuento_pct: Porcentaje de descuento comercial aplicado al subtotal
            antes de calcular el IVA. Rango: 0.0 a 100.0. Por defecto 0.0 (sin descuento).
            Ejemplo: 10.0 representa un descuento del 10%.
        notas: Texto libre para condiciones especiales, plazo de entrega,
            forma de pago u observaciones relevantes para el cliente.
            Ejemplo: "Entrega en 5 dias habiles. Pago a 30 dias."

    Returns:
        Diccionario con la cotizacion completa:
        {
            "numero_cotizacion": str,   # Identificador unico (COT-YYYYMM-XXXX)
            "fecha": str,               # Fecha de emision ISO 8601
            "fecha_vencimiento": str,   # Valida por 30 dias
            "cliente": {
                "nombre": str,
                "empresa": str
            },
            "items_detalle": [          # Lista enriquecida con subtotales
                {
                    "producto": str,
                    "cantidad": int,
                    "precio_unitario": float,
                    "subtotal": float
                }
            ],
            "subtotal": float,          # Suma de todos los subtotales
            "descuento_pct": float,     # Porcentaje aplicado
            "descuento_monto": float,   # Monto descontado
            "base_imponible": float,    # Subtotal menos descuento
            "iva_pct": float,           # Tasa IVA (21%)
            "iva_monto": float,         # Monto de IVA calculado
            "total": float,             # Total final a pagar
            "moneda": str,              # Codigo de moneda
            "notas": str,               # Observaciones
            "estado": str               # "pendiente" (recien generada)
        }

    Raises:
        ValueError: Si items esta vacio, si algun item tiene cantidad <= 0
                    o precio_unitario < 0, o si descuento_pct esta fuera del rango 0-100.

    Example:
        >>> items = [
        ...     {"producto": "Silla ergonomica", "cantidad": 5, "precio_unitario": 120.00},
        ...     {"producto": "Escritorio L", "cantidad": 2, "precio_unitario": 350.00},
        ... ]
        >>> cot = generar_cotizacion("Ana Lopez", "Tech Corp S.A.", items, descuento_pct=5.0)
        >>> print(cot["total"])
        1404.9
    """
    # --- Validaciones ---
    if not items:
        raise ValueError("La lista de items no puede estar vacia.")

    if not (0.0 <= descuento_pct <= 100.0):
        raise ValueError(f"descuento_pct debe estar entre 0 y 100, recibido: {descuento_pct}")

    monedas_validas = {"USD", "EUR", "ARS", "MXN", "CLP", "COP", "PEN", "BRL"}
    if moneda.upper() not in monedas_validas:
        # No bloqueamos, pero normalizamos a mayusculas
        moneda = moneda.upper()
    else:
        moneda = moneda.upper()

    # --- Calcular items ---
    items_detalle = []
    subtotal = 0.0

    for idx, item in enumerate(items):
        producto = str(item.get("producto", f"Producto {idx + 1}")).strip()
        try:
            cantidad = int(item["cantidad"])
            precio_unitario = float(item["precio_unitario"])
        except (KeyError, ValueError, TypeError) as exc:
            raise ValueError(
                f"Item {idx + 1} invalido: se requieren 'cantidad' (int) y "
                f"'precio_unitario' (float). Error: {exc}"
            ) from exc

        if cantidad <= 0:
            raise ValueError(f"Item '{producto}': cantidad debe ser mayor a 0, recibido {cantidad}.")
        if precio_unitario < 0:
            raise ValueError(f"Item '{producto}': precio_unitario no puede ser negativo.")

        item_subtotal = round(cantidad * precio_unitario, 2)
        subtotal += item_subtotal

        items_detalle.append({
            "producto": producto,
            "cantidad": cantidad,
            "precio_unitario": round(precio_unitario, 2),
            "subtotal": item_subtotal,
        })

    subtotal = round(subtotal, 2)

    # --- Descuento ---
    descuento_monto = round(subtotal * (descuento_pct / 100.0), 2)
    base_imponible = round(subtotal - descuento_monto, 2)

    # --- IVA ---
    iva_monto = round(base_imponible * _IVA_RATE, 2)
    total = round(base_imponible + iva_monto, 2)

    # --- Fechas ---
    ahora = datetime.now(timezone.utc)
    fecha_emision = ahora.isoformat()
    fecha_vencimiento = (ahora + timedelta(days=30)).isoformat()

    return {
        "numero_cotizacion": _generar_numero_cotizacion(),
        "fecha": fecha_emision,
        "fecha_vencimiento": fecha_vencimiento,
        "cliente": {
            "nombre": cliente_nombre.strip(),
            "empresa": cliente_empresa.strip(),
        },
        "items_detalle": items_detalle,
        "subtotal": subtotal,
        "descuento_pct": descuento_pct,
        "descuento_monto": descuento_monto,
        "base_imponible": base_imponible,
        "iva_pct": _IVA_RATE * 100,
        "iva_monto": iva_monto,
        "total": total,
        "moneda": moneda,
        "notas": notas.strip(),
        "estado": "pendiente",
    }

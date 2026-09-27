# Formulación del Caso __ (fuente de verdad antes del código)

> Completar y hacer revisar con el subagente `auditor-financiero` antes de implementar `optimizer.py`.
> Cada parámetro debe indicar su clave en input.json.

## 1. Alcance
- Lado(s) del balance que se optimizan:
- Horizonte:
- Qué permanece exógeno:

## 2. Conjuntos e índices
| Símbolo | Descripción |
|---|---|
| $i \in \mathcal{A}$ | activos |
| $j \in \mathcal{L}$ | pasivos |
| $s \in \mathcal{S}$ | escenarios |

## 3. Parámetros
| Símbolo | Descripción | Unidad | Clave input.json |
|---|---|---|---|
| $\lambda$ | aversión al riesgo | – | caseParameters.riskAversionLambda |

## 4. Variables de decisión
| Variable | Descripción | Dominio | Unidad |
|---|---|---|---|

## 5. Función objetivo

## 6. Restricciones
- Pesos (Cuadro 4):
- Comunes: PN ≥ 120; P/A ≤ 0.85; caja ≥ 80; presupuestos; no negatividad.
- Específicas del caso:

## 7. Modelo de riesgo y escenarios

## 8. Supuestos y simplificaciones (con justificación)

## 9. Pruebas que validan la formulación

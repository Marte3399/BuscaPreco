#!/usr/bin/env python3
"""
BuscaPreco - Comparador de precos entre Google Shopping e Amazon.
Busca produtos e exibe resultados ordenados por valor crescente.
"""

import sys
from scrapers.google_shopping import buscar_google_shopping
from scrapers.amazon import buscar_amazon


def buscar_e_comparar(produto, num_resultados=10):
    """Busca produto em todas as fontes e retorna resultados ordenados por preco."""
    print(f"\nBuscando '{produto}'...\n")

    todos_resultados = []

    # Buscar no Google Shopping
    print("[*] Buscando no Google Shopping...")
    resultados_google = buscar_google_shopping(produto, num_resultados)
    print(f"    Encontrados: {len(resultados_google)} resultado(s)")
    todos_resultados.extend(resultados_google)

    # Buscar na Amazon
    print("[*] Buscando na Amazon...")
    resultados_amazon = buscar_amazon(produto, num_resultados)
    print(f"    Encontrados: {len(resultados_amazon)} resultado(s)")
    todos_resultados.extend(resultados_amazon)

    if not todos_resultados:
        print("\nNenhum resultado encontrado.")
        return []

    # Ordenar por valor crescente
    todos_resultados.sort(key=lambda x: x["preco"])

    return todos_resultados


def exibir_resultados(resultados):
    """Exibe os resultados formatados no terminal."""
    if not resultados:
        return

    print("\n" + "=" * 80)
    print(f"{'RESULTADOS ORDENADOS POR PRECO (MENOR -> MAIOR)':^80}")
    print("=" * 80)

    for i, item in enumerate(resultados, 1):
        print(f"\n{i:>3}. {item['nome'][:60]}")
        print(f"     Preco: {item['preco_texto']}")
        print(f"     Fonte: {item['fonte']} | Loja: {item.get('loja', 'N/A')}")
        if item.get("avaliacao"):
            print(f"     Avaliacao: {item['avaliacao']}")
        if item.get("link"):
            print(f"     Link: {item['link'][:80]}")
        print("     " + "-" * 70)

    print(f"\nTotal: {len(resultados)} produto(s) encontrado(s)")
    print(f"Menor preco: {resultados[0]['preco_texto']} ({resultados[0]['fonte']})")
    print(f"Maior preco: {resultados[-1]['preco_texto']} ({resultados[-1]['fonte']})")


def main():
    if len(sys.argv) > 1:
        produto = " ".join(sys.argv[1:])
    else:
        print("=" * 50)
        print("   BuscaPreco - Comparador de Precos")
        print("   Google Shopping + Amazon")
        print("=" * 50)
        produto = input("\nDigite o produto que deseja buscar: ").strip()

    if not produto:
        print("Erro: voce deve informar o nome de um produto.")
        sys.exit(1)

    resultados = buscar_e_comparar(produto)
    exibir_resultados(resultados)


if __name__ == "__main__":
    main()

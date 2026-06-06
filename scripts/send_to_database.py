import generate_routes
from pathlib import Path
import os
import pandas as pd
from opensearchpy import OpenSearch
from opensearchpy.helpers import bulk
import time

#usuwanie warningow
import urllib3
import warnings
warnings.filterwarnings("ignore", category=urllib3.exceptions.InsecureRequestWarning)

BASE_DIR = Path(__file__).resolve().parents[1]
ENV_PATH = BASE_DIR / ".env"

if ENV_PATH.exists():
    for line in ENV_PATH.read_text(encoding="utf-8").splitlines():
        line = line.strip()
        if not line or line.startswith("#") or "=" not in line:
            continue
        key, value = line.split("=", 1)
        os.environ.setdefault(key.strip(), value.strip())

client = OpenSearch(
    hosts=["https://localhost:9200"],
    http_auth=(
        "admin",
        os.getenv("OPENSEARCH_PASSWORD"),
    ),
    use_ssl=True,
    verify_certs=False
)
INDEX_NAME = 'lokalizacje-v1'
CSV = False #false dla danych z generatora,true dla jeżeli używamy danych z pliku csv
# Podmień 'sciezka_do_pliku.csv' na właściwą ścieżkę do Twojego pliku
#CSV_FILE = pd.read_csv('sciezka_do_pliku.csv')

# Generator dla danych z kodu
def doc_generator(dataframe, index_name):
    for index, row in dataframe.iterrows():
        doc = row.to_dict()
        yield {
            "_index": index_name,
            "_source": doc
        }

def print_disk_usage(os_client):
    """Pobiera i wyświetla zajętość dysku w klastrze OpenSearch"""
    print("\n--- ZAJĘTOŚĆ DYSKU OPENSEARCH ---")
    try:
        # Używamy API _cat/allocation z parametrem v (verbose), aby dostać ładne nagłówki
        disk_info = os_client.cat.allocation(v=True, format="text")
        print(disk_info)
    except Exception as e:
        print(f"Nie udało się pobrać informacji o dysku: {e}")
    print("---------------------------------\n")

def main():
    # 1. Dane z generatora
    routes_df = generate_routes.generate_routes()

    # Usunięcie starych indeksów, jeśli istnieją
    if client.indices.exists(index=INDEX_NAME):
        response = client.indices.delete(index=INDEX_NAME)
        print(f"Indeks '{INDEX_NAME}' został usunięty: {response}")
    else:
        print(f"Indeks '{INDEX_NAME}' nie istniał.")

    start = time.time()
    try:
        if CSV == False:
        # Wysłanie danych z generatora tras
            success_routes, errors_routes = bulk(client, doc_generator(routes_df, INDEX_NAME))
            print(f"Sukces! Wysłano dokumentów: {success_routes}")
            if errors_routes:
                print(f"Pojawiły się błędy przy trasach: {errors_routes}")
        else: 
        # Wysłanie danych z pliku CSV
            success_csv, errors_csv = bulk(client, doc_generator(CSV_FILE, INDEX_NAME))
            print(f"Sukces (CSV)! Wysłano dokumentów: {success_csv}")
            if errors_csv:
                print(f"Pojawiły się błędy przy CSV: {errors_csv}")

    except Exception as e:
        print(f"Wystąpił błąd podczas wysyłania: {e}")
        
    end = time.time()
    duration = end - start
    print(f"Wysyłanie danych zajęło: {duration:.4f} sekund")

    total_docs = success_routes #+ success_csv
    if total_docs > 0:
        avg_time_per_point = duration / total_docs
        print(f"Średni czas wstawiania jednego punktu: {avg_time_per_point:.6f} sekund")

    # Sprawdzenie zajętości dysku
    print_disk_usage(client)

if __name__ == "__main__":
    main()

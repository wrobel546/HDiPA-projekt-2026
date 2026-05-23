# Generator tras robotów

Generator znajduje się w pliku:

```text
scripts/generate_routes.py
```

Skrypt generuje syntetyczne trasy robotów poruszających się po zadanym obszarze geograficznym.  
Dla każdego robota tworzony jest zestaw punktów zawierających czas próbki oraz współrzędne pozycji.

Wygenerowane dane są zapisywane do pliku CSV, a dodatkowo tworzony jest wykres tras robotów w formacie PNG.

## Format danych wyjściowych

Plik CSV ma następujący format:

```csv
Id,timestamp,latitude,longitude
1,1714398000.523,52.4015141,16.951442
1,1714398000.623,52.4015155,16.9514433
```

Znaczenie kolumn:

- `Id` - identyfikator robota,
- `timestamp` - czas próbki jako Unix timestamp,
- `latitude` - szerokość geograficzna,
- `longitude` - długość geograficzna.

## Wymagania

Do uruchomienia skryptu wymagany jest Python oraz biblioteki:

```text
numpy
pandas
matplotlib
```

Instalacja zależności:

```bash
pip install numpy pandas matplotlib
```

## Uruchomienie

Skrypt uruchamia się z katalogu głównego projektu:

```bash
python scripts/generate_routes.py
```

Po uruchomieniu skrypt:

1. generuje dane tras robotów,
2. zapisuje dane do pliku CSV,
3. generuje wykres tras,
4. wypisuje podstawowe informacje oraz statystyki w konsoli.

## Pliki wynikowe

Po uruchomieniu skrypt zapisuje wyniki do plików:

```text
data/generated/generated_routes_sample.csv
reports/generated_routes_sample.png
```

Plik CSV zawiera wygenerowane punkty tras robotów.  
Plik PNG zawiera wizualizację tras na wykresie.

## Parametry generatora

Parametry generatora znajdują się na początku pliku `scripts/generate_routes.py`:

```python
NUM_ROBOTS = 10
START_TS = 1714398000.523
END_TS = START_TS + 100
INTERVAL_SECONDS = 0.1

AVG_ACTIVE_ROBOTS = 5

LAT_MIN = 52.401220
LAT_MAX = 52.401965
LON_MIN = 16.951101
LON_MAX = 16.952410

RANDOM_SEED = 22
```

Opis parametrów:

- `NUM_ROBOTS` - liczba robotów, dla których zostaną wygenerowane trasy.
- `START_TS` - początek symulacji jako Unix timestamp.
- `END_TS` - koniec symulacji jako Unix timestamp.
- `INTERVAL_SECONDS` - odstęp czasu między kolejnymi próbkami pozycji.
- `AVG_ACTIVE_ROBOTS` - przybliżona średnia liczba robotów aktywnych w tym samym czasie.
- `LAT_MIN`, `LAT_MAX` - minimalna i maksymalna szerokość geograficzna obszaru.
- `LON_MIN`, `LON_MAX` - minimalna i maksymalna długość geograficzna obszaru.
- `RANDOM_SEED` - ziarno losowości pozwalające uzyskać powtarzalne wyniki.

## Zasada działania

Generator tworzy trasę osobno dla każdego robota.

Dla robota wyznaczany jest przedział czasu aktywności. Długość tego przedziału zależy od wartości `AVG_ACTIVE_ROBOTS` oraz `NUM_ROBOTS`:

```text
route_time = (END_TS - START_TS) * min(AVG_ACTIVE_ROBOTS, NUM_ROBOTS) / NUM_ROBOTS
```

Każdy robot otrzymuje inne przesunięcie startu w czasie, dzięki czemu roboty nie zaczynają ruchu dokładnie w tym samym momencie.

Na początku trasy robot otrzymuje losową pozycję startową w obrębie bezpiecznego obszaru. Następnie w każdej próbce:

1. lekko zmieniany jest kierunek ruchu,
2. lekko zmieniana jest prędkość,
3. obliczana jest nowa pozycja,
4. pozycja jest ograniczana do dozwolonego obszaru,
5. punkt zostaje zapisany do wyniku.

## Ograniczenie obszaru ruchu

Roboty poruszają się w obszarze określonym przez:

```python
LAT_MIN
LAT_MAX
LON_MIN
LON_MAX
```

Dodatkowo generator wyznacza bezpieczny margines równy 10% rozmiaru obszaru.  
Jeśli robot próbuje wyjść poza ten margines, jego kierunek zostaje zmieniony tak, aby pozostał w dozwolonym zakresie.

## Wizualizacja

Wykres tras zapisywany jest do pliku:

```text
reports/generated_routes_sample.png
```

Na wykresie:

- oś X odpowiada wartości `lon`,
- oś Y odpowiada wartości `lat`,
- każdy robot jest oznaczony innym kolorem.

Kolory generowane są dynamicznie na podstawie liczby robotów, więc nie ma stałego ograniczenia liczby kolorów.

Jeśli liczba robotów jest mniejsza lub równa 15, na wykresie dodawana jest legenda z identyfikatorami robotów.  
Dla większej liczby robotów legenda jest pomijana, żeby nie zasłaniała wykresu.

## Wynik w konsoli

Po uruchomieniu skrypt wypisuje między innymi:

```text
Liczba wygenerowanych punktow
Liczba robotow
Zakres czasu
Sciezka do zapisanego pliku CSV
Sciezka do zapisanego wykresu
```

Dodatkowo wypisywane jest podsumowanie dla każdego robota:

```text
points_count
start_time
end_time
min_lat
max_lat
min_lon
max_lon
```

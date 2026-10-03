# Zmiany

## 1.0.0

Pierwsze wydanie.

- Powiadomienia na Telegramie o wejściach i wyjściach graczy na instancjach AMP (CubeCoders):
  nick, czas gry, SteamID (Valheim), UUID (Minecraft).
- Reguły rozpoznawania graczy brane automatycznie z plików `.kvp` instancji AMP, więc nowe gry
  zwykle działają od razu; Minecraft i dodatki dla Valheima wbudowane. Ostrzeżenie, gdy
  nowej gry nie da się rozpoznać.
- 🆕 alert o graczu, którego bot jeszcze nie widział, 💀 śmierci (Valheim, Minecraft).
- Przy starcie bot odczytuje bieżący log, więc wie, kto już gra.
- Komendy: `/online`, `/status`, `/historia`, `/gracz`, `/tydzien`, `/wersja`, `/update`,
  `/rollback`, `/pomoc`; menu komend i klawiatura tylko dla admina; obcy dostają odmowę,
  a admin raz dowiaduje się, kto pisał.
- Podsumowanie tygodnia w niedzielę wieczorem.
- Pilnowanie laptopa: bateria poniżej progu, temperatura CPU, tunel playit.gg.
- Aktualizacja z GitHuba: `/update` na Telegramie albo `amp-tg-bot-update` w terminalu; nowa
  wersja jest testowana przed podmianą, stara zostaje jako kopia do `/rollback`.

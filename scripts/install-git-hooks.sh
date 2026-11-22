#!/usr/bin/env bash
set -e

HOOK_PATH=".git/hooks/pre-commit"

echo "Instalacja lokalnego hooka pre-commit w ${HOOK_PATH}..."

cat << 'EOF' > "${HOOK_PATH}"
#!/usr/bin/env bash
# Git pre-commit hook dla OBD2-AI: weryfikacja składni (py_compile) i lintera (ruff)

STAGED_PY_FILES=$(git diff --cached --name-only --diff-filter=ACM | grep '\.py$' || true)

if [ -z "$STAGED_PY_FILES" ]; then
    exit 0
fi

echo "🔍 [Pre-Commit Hook] Weryfikacja zmienionych plików Pythona..."

# 1. Twarda weryfikacja składni (SyntaxError, unclosed parentheses)
for file in $STAGED_PY_FILES; do
    if [ -f "$file" ]; then
        python3 -m py_compile "$file" || {
            echo "❌ [Pre-Commit Hook] BŁĄD SKŁADNI (SyntaxError) w pliku: $file"
            echo "Commit został zablokowany. Popraw błąd przed commitem!"
            exit 1
        }
    fi
done

# 2. Weryfikacja linterem Ruff (jeśli zainstalowany)
if command -v ruff &> /dev/null; then
    ruff check $STAGED_PY_FILES || {
        echo "❌ [Pre-Commit Hook] Naruszenie reguł lintera Ruff."
        echo "Uruchom: ruff check --fix lub popraw błędy ręcznie!"
        exit 1
    }
fi

echo "✅ [Pre-Commit Hook] Wszystkie sprawdzane pliki są poprawne."
exit 0
EOF

chmod +x "${HOOK_PATH}"
echo "✅ Hook pre-commit zainstalowany pomyślnie."

package api

import (
	"bytes"
	"encoding/json"
	"net/http"
	"net/http/httptest"
	"testing"

	"github.com/SMCodesP/brscans-backend/internal/app"
)

func newTestRouter() http.Handler {
	return NewRouter(app.NewStore())
}

func TestHealthz(t *testing.T) {
	r := newTestRouter()
	req := httptest.NewRequest(http.MethodGet, "/healthz", nil)
	rr := httptest.NewRecorder()
	r.ServeHTTP(rr, req)

	if rr.Code != http.StatusOK {
		t.Fatalf("expected %d, got %d", http.StatusOK, rr.Code)
	}
}

func TestManhwaCRUDAndNestedChapters(t *testing.T) {
	r := newTestRouter()

	manhwaBody := bytes.NewBufferString(`{"title":"Solo Leveling","slug":"solo-leveling"}`)
	createManhwaReq := httptest.NewRequest(http.MethodPost, "/manhwas", manhwaBody)
	createManhwaReq.Header.Set("Content-Type", "application/json")
	createManhwaRes := httptest.NewRecorder()
	r.ServeHTTP(createManhwaRes, createManhwaReq)
	if createManhwaRes.Code != http.StatusCreated {
		t.Fatalf("expected %d, got %d", http.StatusCreated, createManhwaRes.Code)
	}

	var createdManhwa map[string]any
	if err := json.Unmarshal(createManhwaRes.Body.Bytes(), &createdManhwa); err != nil {
		t.Fatalf("failed to decode manhwa: %v", err)
	}
	manhwaID := int(createdManhwa["id"].(float64))

	chapterBody := bytes.NewBufferString(`{"manhwa_id":1,"number":1,"title":"Chapter 1"}`)
	createChapterReq := httptest.NewRequest(http.MethodPost, "/chapters", chapterBody)
	createChapterReq.Header.Set("Content-Type", "application/json")
	createChapterRes := httptest.NewRecorder()
	r.ServeHTTP(createChapterRes, createChapterReq)
	if createChapterRes.Code != http.StatusCreated {
		t.Fatalf("expected %d, got %d", http.StatusCreated, createChapterRes.Code)
	}

	nestedReq := httptest.NewRequest(http.MethodGet, "/manhwas/"+itoa(manhwaID)+"/chapters", nil)
	nestedRes := httptest.NewRecorder()
	r.ServeHTTP(nestedRes, nestedReq)
	if nestedRes.Code != http.StatusOK {
		t.Fatalf("expected %d, got %d", http.StatusOK, nestedRes.Code)
	}

	var Chapters []map[string]any
	if err := json.Unmarshal(nestedRes.Body.Bytes(), &Chapters); err != nil {
		t.Fatalf("failed to decode Chapters: %v", err)
	}
	if len(Chapters) != 1 {
		t.Fatalf("expected 1 chapter, got %d", len(Chapters))
	}
}

func TestFavoriteFlow(t *testing.T) {
	r := newTestRouter()

	registerReq := httptest.NewRequest(http.MethodPost, "/auth/register", bytes.NewBufferString(`{"username":"sam","password":"123"}`))
	registerReq.Header.Set("Content-Type", "application/json")
	registerRes := httptest.NewRecorder()
	r.ServeHTTP(registerRes, registerReq)
	if registerRes.Code != http.StatusCreated {
		t.Fatalf("expected %d, got %d", http.StatusCreated, registerRes.Code)
	}

	createManhwaReq := httptest.NewRequest(http.MethodPost, "/manhwas", bytes.NewBufferString(`{"title":"A","slug":"a"}`))
	createManhwaReq.Header.Set("Content-Type", "application/json")
	createManhwaRes := httptest.NewRecorder()
	r.ServeHTTP(createManhwaRes, createManhwaReq)
	if createManhwaRes.Code != http.StatusCreated {
		t.Fatalf("expected %d, got %d", http.StatusCreated, createManhwaRes.Code)
	}

	favoriteReq := httptest.NewRequest(http.MethodPost, "/manhwas/1/favorite", nil)
	favoriteReq.Header.Set("X-User-ID", "1")
	favoriteRes := httptest.NewRecorder()
	r.ServeHTTP(favoriteRes, favoriteReq)
	if favoriteRes.Code != http.StatusOK {
		t.Fatalf("expected %d, got %d", http.StatusOK, favoriteRes.Code)
	}

	favoritesReq := httptest.NewRequest(http.MethodGet, "/favorites", nil)
	favoritesReq.Header.Set("X-User-ID", "1")
	favoritesRes := httptest.NewRecorder()
	r.ServeHTTP(favoritesRes, favoritesReq)
	if favoritesRes.Code != http.StatusOK {
		t.Fatalf("expected %d, got %d", http.StatusOK, favoritesRes.Code)
	}

	var Favorites []map[string]any
	if err := json.Unmarshal(favoritesRes.Body.Bytes(), &Favorites); err != nil {
		t.Fatalf("failed to decode Favorites: %v", err)
	}
	if len(Favorites) != 1 {
		t.Fatalf("expected 1 favorite, got %d", len(Favorites))
	}
}

func itoa(n int) string {
	if n == 0 {
		return "0"
	}
	neg := false
	if n < 0 {
		neg = true
		n = -n
	}
	buf := make([]byte, 0, 12)
	for n > 0 {
		buf = append([]byte{byte('0' + (n % 10))}, buf...)
		n /= 10
	}
	if neg {
		buf = append([]byte{'-'}, buf...)
	}
	return string(buf)
}

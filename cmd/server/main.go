package main

import (
	"log"
	"net/http"
	"os"

	"github.com/SMCodesP/brscans-backend/internal/api"
	"github.com/SMCodesP/brscans-backend/internal/app"
)

func main() {
	store := app.NewStore()
	router := api.NewRouter(store)

	port := os.Getenv("PORT")
	if port == "" {
		port = "8080"
	}

	addr := ":" + port
	log.Printf("brscans-backend Go server listening on %s", addr)
	if err := http.ListenAndServe(addr, router); err != nil {
		log.Fatal(err)
	}
}

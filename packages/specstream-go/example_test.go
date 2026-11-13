package specstream_test

import (
	"context"
	"fmt"
	"log"
	"os"

	specstream "github.com/specstream/specstream-tools/packages/specstream-go"
)

func ExampleClient_Search() {
	client, err := specstream.NewClient(os.Getenv("SPECSTREAM_API_KEY"))
	if err != nil {
		log.Fatal(err)
	}
	found, err := client.Search(context.Background(), "What is the population of Japan?", nil)
	if err != nil {
		log.Fatal(err)
	}
	if found.Answer != nil {
		fmt.Println(found.Answer.Value, found.Answer.Page)
	}
	for _, source := range found.Sources {
		fmt.Println(source.Title, source.URL)
	}
}

func ExampleClient_Extract() {
	client, err := specstream.NewClient(os.Getenv("SPECSTREAM_API_KEY"))
	if err != nil {
		log.Fatal(err)
	}
	pages, err := client.Extract(context.Background(), specstream.ExtractRequest{
		URLs: []string{"https://example.com"},
	})
	if err != nil {
		log.Fatal(err)
	}
	for _, page := range pages.Results {
		if page.OK() {
			fmt.Println(page.Title, len(page.Text))
		}
	}
}

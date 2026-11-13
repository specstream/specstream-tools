//! cargo run --example search -- "What is the population of Japan?"
//! Needs SPECSTREAM_API_KEY in the environment.

use specstream::{Client, WebSearch};

fn main() -> Result<(), specstream::Error> {
    let question = std::env::args()
        .nth(1)
        .unwrap_or_else(|| "What is the population of Japan?".into());
    let client = Client::from_env()?;
    let answer = client.web_search(&WebSearch::new(question))?;
    for source in answer["sources"].as_array().into_iter().flatten().take(3) {
        println!("{}\n  {}", source["title"], source["url"]);
    }
    Ok(())
}

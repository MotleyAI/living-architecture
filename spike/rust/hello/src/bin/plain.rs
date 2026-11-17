//! The plain binary the console scripts' start-up is compared with.

#[path = "../greeting.rs"]
mod greeting;

fn main() {
    println!("{}", greeting::greeting());
}

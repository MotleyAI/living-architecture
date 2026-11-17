//! The packaging probe: one abi3 module, `dr_hello`, whose functions back the `dr-hello` console scripts.

mod greeting;

#[pyo3::pymodule]
mod dr_hello {
    use pyo3::prelude::*;

    #[pyfunction]
    fn greeting() -> &'static str {
        super::greeting::greeting()
    }

    /// The `dr-hello` console script.
    #[pyfunction]
    fn main() {
        println!("{}", super::greeting::greeting());
    }

    /// The `dr-hello-two` console script.
    #[pyfunction]
    fn main_two() {
        println!("{}", super::greeting::greeting());
    }
}

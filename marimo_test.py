import marimo

__generated_with = "0.24.2"
app = marimo.App(width="medium")


@app.cell
def _():
    import marimo as mo

    return


@app.cell
def _():
    from huggingface_hub import snapshot_download

    folder = snapshot_download("Cahol/laya-banking77-v1", local_dir="laya-banking77-v1")
    print(folder)

    return


@app.cell
def _():
    return


@app.cell
def _():
    return


@app.cell
def _():
    return


if __name__ == "__main__":
    app.run()

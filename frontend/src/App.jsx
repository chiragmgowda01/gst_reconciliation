import { useEffect, useState } from "react";
import "./App.css";

function App() {
  const [data, setData] = useState(null);
  const [gstr3b, setGstr3b] = useState(null);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState("");

  useEffect(() => {
    Promise.all([
      fetch("http://localhost:8000/reconcile"),
      fetch("http://localhost:8000/gstr3b/summary")
    ])
      .then(async ([r1, r2]) => {
        if (!r1.ok || !r2.ok) {
          throw new Error("Backend API error");
        }

        const reconciliation = await r1.json();
        const summary = await r2.json();

        setData(reconciliation);
        setGstr3b(summary);
        setLoading(false);
      })
      .catch((err) => {
        setError(err.message);
        setLoading(false);
      });
  }, []);

  if (loading) {
    return <h2 className="loading">Loading GST data...</h2>;
  }

  if (error) {
    return <h2 className="error">Error: {error}</h2>;
  }

  const sales = data?.sales || [];
  const purchases = data?.purchases || [];

  const all = [...sales, ...purchases];

  const matched = all.filter((x) => x.status === "MATCH").length;
  const mismatched = all.filter((x) => x.status === "MISMATCH").length;
  const missing = all.filter((x) => x.status === "MISSING_IN_GST").length;
  const extra = all.filter((x) => x.status === "EXTRA_IN_GST").length;

  return (
    <div className="app">

      <header>
        <h1>GST Reconciliation System</h1>
        <p>
          Automated MSME GST Reconciliation and Anomaly Detector
        </p>
      </header>

      <div className="cards">

        <div className="card">
          <h3>Total Records</h3>
          <h2>{all.length}</h2>
        </div>

        <div className="card">
          <h3>Matched</h3>
          <h2>{matched}</h2>
        </div>

        <div className="card">
          <h3>Mismatched</h3>
          <h2>{mismatched}</h2>
        </div>

        <div className="card">
          <h3>Missing</h3>
          <h2>{missing}</h2>
        </div>

        <div className="card">
          <h3>Extra</h3>
          <h2>{extra}</h2>
        </div>

      </div>

      <section>
        <h2>Sales Reconciliation</h2>

        <table>
          <thead>
            <tr>
              <th>Invoice No</th>
              <th>Status</th>
              <th>Taxable Difference</th>
              <th>GST Difference</th>
            </tr>
          </thead>

          <tbody>
            {sales.map((row) => (
              <tr key={row.invoice_no}>
                <td>{row.invoice_no}</td>
                <td>
                  <span className={"status " + row.status}>
                    {row.status}
                  </span>
                </td>
                <td>{row.taxable_value_diff ?? "-"}</td>
                <td>{row.gst_amount_diff ?? "-"}</td>
              </tr>
            ))}
          </tbody>
        </table>
      </section>

      <section>
        <h2>Purchase Reconciliation</h2>

        <table>
          <thead>
            <tr>
              <th>Invoice No</th>
              <th>Status</th>
              <th>Taxable Difference</th>
              <th>GST Difference</th>
            </tr>
          </thead>

          <tbody>
            {purchases.map((row) => (
              <tr key={row.invoice_no}>
                <td>{row.invoice_no}</td>
                <td>
                  <span className={"status " + row.status}>
                    {row.status}
                  </span>
                </td>
                <td>{row.taxable_value_diff ?? "-"}</td>
                <td>{row.gst_amount_diff ?? "-"}</td>
              </tr>
            ))}
          </tbody>
        </table>
      </section>

      <section>
        <h2>GSTR-3B Summary</h2>

        {gstr3b && (
          <div className="cards">

            <div className="card">
              <h3>Tax Period</h3>
              <h2>{gstr3b.tax_period}</h2>
            </div>

            <div className="card">
              <h3>Output Tax</h3>
              <h2>₹{gstr3b.output_tax}</h2>
            </div>

            <div className="card">
              <h3>Eligible ITC</h3>
              <h2>₹{gstr3b.eligible_itc}</h2>
            </div>

            <div className="card">
              <h3>ITC Reversed</h3>
              <h2>₹{gstr3b.itc_reversed}</h2>
            </div>

            <div className="card">
              <h3>Net ITC</h3>
              <h2>₹{gstr3b.net_itc}</h2>
            </div>

          </div>
        )}
      </section>

    </div>
  );
}

export default App;
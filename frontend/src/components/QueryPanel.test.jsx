import { renderToStaticMarkup } from "react-dom/server";
import { describe, expect, it } from "vitest";
import QueryPanel from "./QueryPanel";

const SQL_RUN = {
  kind: "sql",
  query: "SELECT region, SUM(revenue) AS total FROM sales_q1 GROUP BY region",
  columns: ["region", "total"],
  rows: [
    ["North", 120000],
    ["South", null],
  ],
  row_count: 2,
  truncated: false,
  error: null,
  tables: [{ filename: "sales.xlsx", page: 1 }],
};

const MONGO_RUN = {
  kind: "mongodb",
  query: "SELECT filename AS \"File\" FROM chunks ORDER BY \"Score\" DESC LIMIT 4;",
  columns: ["File", "Page", "Score", "Excerpt"],
  rows: [["handbook.pdf", 2, 0.912, "Every full-time employee receives 24 days"]],
  row_count: 1,
};

const render = (queries) => renderToStaticMarkup(<QueryPanel queries={queries} />);

describe("QueryPanel", () => {
  it("shows the SQL, the source file and the result table", () => {
    const html = render([SQL_RUN]);
    expect(html).toContain("SQL query");
    expect(html).toContain("sales.xlsx");
    expect(html).toContain("SELECT region, SUM(revenue) AS total FROM sales_q1 GROUP BY region");
    expect(html).toContain("<th");
    expect(html).toContain("region");
    expect(html).toContain("120000");
    expect(html).toContain("2 rows");
  });

  it("shows the document search as SQL and the passages it returned", () => {
    const html = render([MONGO_RUN]);
    expect(html).toContain("SQL query");
    expect(html).not.toContain("MongoDB");
    expect(html).toContain("FROM chunks");
    expect(html).toContain("handbook.pdf");
    expect(html).toContain("0.912");
    expect(html).toContain("1 row");
    expect(html).not.toContain("1 rows");
  });

  it("names the selected file a MongoDB search was limited to", () => {
    const html = render([{ ...MONGO_RUN, label: "handbook.pdf (selected file)" }, { ...MONGO_RUN, label: "all documents" }]);
    expect(html).toContain("handbook.pdf (selected file)");
    expect(html).toContain("all documents");
  });

  it("says when only part of the result is shown", () => {
    const rows = Array.from({ length: 50 }, (_, i) => [i]);
    const html = render([{ ...SQL_RUN, columns: ["n"], rows, row_count: 200, truncated: true }]);
    expect(html).toContain("Showing 50 of 200+ rows");
  });

  it("shows a failed query's error instead of a table", () => {
    const html = render([{ ...SQL_RUN, columns: [], rows: [], row_count: 0, error: "no such column: nope" }, MONGO_RUN]);
    expect(html).toContain("no such column: nope");
    expect(html.match(/SQL query/g)).toHaveLength(2);
    expect(html.match(/<table/g)).toHaveLength(1);
  });

  it("renders nothing without queries", () => {
    expect(render([])).toBe("");
    expect(render(undefined)).toBe("");
  });
});

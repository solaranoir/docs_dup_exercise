import { Link } from "../components/Link";
import { paths } from "../router";
import { useDocumentTitle } from "../useDocumentTitle";

export function NotFound() {
  useDocumentTitle("Page not found");
  return (
    <div className="not-found">
      <h1>Page not found</h1>
      <p>There's nothing at this address. It may have been mistyped, or the link may be out of date.</p>
      <Link to={paths.list}>Go to My Documents</Link>
    </div>
  );
}

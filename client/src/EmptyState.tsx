export function Empty({
  title,
  description,
}: {
  title: string;
  description: string;
}) {
  return (
    <div className="empty-state">
      <img className="empty-pig" src="/brand/mark.png" alt="" />
      <h3>{title}</h3>
      <p>{description}</p>
    </div>
  );
}

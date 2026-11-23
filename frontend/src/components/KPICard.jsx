export function KPICard({
  title,
  value,
  icon: Icon,
  subtext,
  iconBg = "#eff6ff",
  iconColor = "#2563eb",
  accentColor = "var(--primary-blue)",
}) {
  return (
    <div className="kpi-card" style={accentColor ? { borderTop: `3px solid ${accentColor}` } : {}}>
      <div className="kpi-header">
        <span className="kpi-title">{title}</span>
        {Icon && (
          <div className="kpi-icon-wrap" style={{ backgroundColor: iconBg, color: iconColor }}>
            <Icon size={17} />
          </div>
        )}
      </div>
      <div className="kpi-value">{value}</div>
      {subtext && <div className="kpi-subtext">{subtext}</div>}
    </div>
  );
}
export default KPICard;

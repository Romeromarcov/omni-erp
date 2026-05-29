import { describe, it, expect, vi } from 'vitest';
import { render, screen, fireEvent } from '@testing-library/react';
import Pagination from '../components/Pagination';

describe('Pagination', () => {
  it('renders nothing when count <= pageSize (only 1 page)', () => {
    const { container } = render(
      <Pagination page={1} count={10} pageSize={20} onChange={vi.fn()} />
    );
    expect(container.firstChild).toBeNull();
  });

  it('renders pagination when count > pageSize', () => {
    render(<Pagination page={1} count={50} pageSize={20} onChange={vi.fn()} />);
    // Should show page buttons
    expect(screen.getByText('1')).toBeInTheDocument();
    expect(screen.getByText('2')).toBeInTheDocument();
    expect(screen.getByText('3')).toBeInTheDocument();
  });

  it('disables prev button on first page', () => {
    render(<Pagination page={1} count={100} pageSize={20} onChange={vi.fn()} />);
    const prevBtn = screen.getByRole('button', { name: /go to previous page/i });
    expect(prevBtn).toBeDisabled();
  });

  it('disables next button on last page', () => {
    render(<Pagination page={5} count={100} pageSize={20} onChange={vi.fn()} />);
    const nextBtn = screen.getByRole('button', { name: /go to next page/i });
    expect(nextBtn).toBeDisabled();
  });

  it('calls onChange with next page when next is clicked', () => {
    const onChange = vi.fn();
    render(<Pagination page={2} count={100} pageSize={20} onChange={onChange} />);
    fireEvent.click(screen.getByRole('button', { name: /go to next page/i }));
    expect(onChange).toHaveBeenCalledWith(3);
  });

  it('calls onChange with prev page when prev is clicked', () => {
    const onChange = vi.fn();
    render(<Pagination page={3} count={100} pageSize={20} onChange={onChange} />);
    fireEvent.click(screen.getByRole('button', { name: /go to previous page/i }));
    expect(onChange).toHaveBeenCalledWith(2);
  });

  it('calls onChange with specific page when a page button is clicked', () => {
    const onChange = vi.fn();
    render(<Pagination page={1} count={100} pageSize={20} onChange={onChange} />);
    fireEvent.click(screen.getByText('3'));
    expect(onChange).toHaveBeenCalledWith(3);
  });

  it('shows total count and page info', () => {
    render(<Pagination page={2} count={85} pageSize={20} onChange={vi.fn()} />);
    expect(screen.getByText(/85 registros/)).toBeInTheDocument();
    expect(screen.getByText(/pág 2/)).toBeInTheDocument();
  });

  it('shows ellipsis for many pages', () => {
    render(<Pagination page={5} count={300} pageSize={20} onChange={vi.fn()} />);
    expect(screen.getAllByText('…').length).toBeGreaterThanOrEqual(1);
  });
});
